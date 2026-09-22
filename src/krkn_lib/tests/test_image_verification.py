import base64
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from krkn_lib.k8s.image_verification import (
    CosignImageVerifier,
    ImageSignatureVerificationError,
)
from krkn_lib.k8s.krkn_kubernetes import KrknKubernetes


class ImageVerificationTests(unittest.TestCase):
    def setUp(self):
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.private_key.public_key()
        self.public_key_pem = self.public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def test_verifies_ecdsa_signature(self):
        payload = b"cosign payload"
        signature = self.private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        verifier = CosignImageVerifier(self.public_key_pem)

        self.assertTrue(verifier._verify_signature(signature, payload))

    def test_loads_production_public_key_fixture(self):
        key_path = (
            Path(__file__).resolve().parents[2] / "testdata" / "cosign.pub"
        )

        verifier = CosignImageVerifier(str(key_path))

        self.assertIsNotNone(verifier._public_key)

    def test_rejects_tampered_payload(self):
        payload = b"cosign payload"
        signature = self.private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        verifier = CosignImageVerifier(self.public_key_pem)

        self.assertFalse(verifier._verify_signature(signature, b"tampered"))

    def test_verifies_cosign_dsse_bundle(self):
        image_digest = "sha256:" + ("a" * 64)
        payload_type = "application/vnd.in-toto+json"
        payload = json.dumps(
            {
                "_type": "https://in-toto.io/Statement/v1",
                "subject": [{"digest": {"sha256": "a" * 64}}],
                "predicateType": "https://sigstore.dev/cosign/sign/v1",
                "predicate": {},
            },
            separators=(",", ":"),
        ).encode()
        pae = b" ".join(
            [
                b"DSSEv1",
                str(len(payload_type)).encode(),
                payload_type.encode(),
                str(len(payload)).encode(),
                payload,
            ]
        )
        signature = self.private_key.sign(pae, ec.ECDSA(hashes.SHA256()))
        bundle = {
            "verificationMaterial": {"publicKey": {"hint": "test"}},
            "dsseEnvelope": {
                "payload": base64.b64encode(payload).decode(),
                "payloadType": payload_type,
                "signatures": [{"sig": base64.b64encode(signature).decode()}],
            },
        }

        verifier = CosignImageVerifier(self.public_key_pem)

        self.assertTrue(
            verifier._verify_bundle(json.dumps(bundle).encode(), image_digest)
        )

    @patch("krkn_lib.k8s.krkn_kubernetes.CosignImageVerifier")
    def test_kubernetes_method_returns_boolean(self, verifier_class):
        verifier_class.return_value.verify.return_value = True

        result = KrknKubernetes.verify_image_signature(
            self.public_key_pem, "quay.io/example/image:latest"
        )

        self.assertIs(result, True)
        verifier_class.assert_called_once_with(self.public_key_pem)
        verifier_class.return_value.verify.assert_called_once_with(
            "quay.io/example/image:latest"
        )

    def test_kubernetes_method_rejects_invalid_key(self):
        self.assertIs(
            KrknKubernetes.verify_image_signature(
                b"not a PEM key", "quay.io/example/image:latest"
            ),
            False,
        )

    def test_extracts_unique_images_from_nested_manifest(self):
        manifest = {
            "spec": {
                "containers": [
                    {"image": "quay.io/example/workload:latest"},
                    {"image": "quay.io/example/workload:latest"},
                ],
                "initContainers": [
                    {"image": "quay.io/example/init:latest"},
                ],
            }
        }

        self.assertEqual(
            KrknKubernetes._extract_manifest_images(manifest),
            [
                "quay.io/example/workload:latest",
                "quay.io/example/init:latest",
            ],
        )

    def test_manifest_verification_fails_before_deploy(self):
        kubernetes = KrknKubernetes.__new__(KrknKubernetes)
        kubernetes._image_signature_verification_enabled = True
        kubernetes._image_signature_verifier = Mock(verify=lambda image: False)
        kubernetes._image_signature_bypass_warning_logged = False

        with self.assertRaises(ImageSignatureVerificationError):
            kubernetes._verify_manifest_images(
                {"spec": {"containers": [{"image": "quay.io/example/image"}]}},
                "creating pod",
            )


if __name__ == "__main__":
    unittest.main()

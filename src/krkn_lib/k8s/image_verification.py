"""Pure-Python verification of Cosign-signed OCI images."""

import base64
import hashlib
import json
import logging
import os
from typing import Any, Optional

import oras.provider
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, ed448, rsa
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15

LOGGER = logging.getLogger(__name__)

_SIGNATURE_MEDIA_TYPE = "application/vnd.dev.cosign.simplesigning.v1+json"
_BUNDLE_MEDIA_TYPE = "application/vnd.dev.sigstore.bundle"
_SIGNATURE_ANNOTATION = "dev.cosignproject.cosign/signature"
_IMAGE_INDEX_MEDIA_TYPES = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)


class ImageSignatureVerificationError(RuntimeError):
    """Raised when an image required by a workload is not trusted."""


class CosignImageVerifier:
    """Verify key-based Cosign signatures without invoking external binaries."""

    def __init__(self, public_key: str | bytes):
        self._public_key = self._load_public_key(public_key)

    @staticmethod
    def _load_public_key(public_key: str | bytes) -> Any:
        if isinstance(public_key, str) and os.path.isfile(public_key):
            with open(public_key, "rb") as key_file:
                public_key = key_file.read()
        if isinstance(public_key, str):
            public_key = public_key.encode("utf-8")
        return serialization.load_pem_public_key(public_key)

    def verify(self, image: str) -> bool:
        """Return whether ``image`` has a valid signature for this key."""
        try:
            registry = oras.provider.Registry()
            container = registry.get_container(image)
            manifest = registry.get_manifest(container)
            digest = self._manifest_digest(registry, container, manifest)

            bundle_found, bundle_verified = self._verify_referrer_bundles(
                registry, container, digest
            )
            if bundle_found:
                return bundle_verified
            return self._verify_legacy_signature(registry, container, digest)
        except Exception:  # Verification is deliberately fail-closed.
            LOGGER.debug(
                "Unable to verify image signature for %s", image, exc_info=True
            )
            return False

    @staticmethod
    def _manifest_digest(
        registry: oras.provider.Registry,
        container: Any,
        manifest: dict,
    ) -> str:
        if container.digest:
            return container.digest

        response = registry.do_request(
            f"https://{container.manifest_url(container.tag)}",
            "HEAD",
            headers={"Accept": ", ".join(_IMAGE_INDEX_MEDIA_TYPES)},
        )
        response.raise_for_status()
        digest = response.headers.get("Docker-Content-Digest")
        if digest:
            return digest

        encoded = json.dumps(
            manifest, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def _verify_referrer_bundles(
        self, registry: oras.provider.Registry, container: Any, digest: str
    ) -> tuple[bool, bool]:
        """Verify Cosign's OCI 1.1 message-signature bundle, when present."""
        url = (
            f"https://{container.registry}/v2/{container.api_prefix}"
            f"/referrers/{digest}"
        )
        response = registry.do_request(
            url,
            "GET",
            headers={"Accept": "application/vnd.oci.image.index.v1+json"},
        )
        if response.status_code == 404:
            return False, False
        response.raise_for_status()
        index = response.json()
        bundle_found = False

        for descriptor in index.get("manifests", []):
            artifact_type = descriptor.get("artifactType", "")
            if not artifact_type.startswith(_BUNDLE_MEDIA_TYPE):
                continue
            bundle_found = True
            if descriptor.get("subject", {}).get("digest", digest) != digest:
                continue
            bundle_manifest = self._get_manifest(
                registry, container, descriptor["digest"]
            )
            for layer in bundle_manifest.get("layers", []):
                if not layer.get("mediaType", "").startswith(
                    _BUNDLE_MEDIA_TYPE
                ):
                    continue
                bundle = self._get_blob(registry, container, layer["digest"])
                if self._verify_bundle(bundle, digest):
                    return True, True
        return bundle_found, False

    def _verify_legacy_signature(
        self, registry: oras.provider.Registry, container: Any, digest: str
    ) -> bool:
        signature_tag = digest.replace(":", "-") + ".sig"
        try:
            signature_manifest = self._get_manifest(
                registry, container, signature_tag
            )
        except Exception:
            return False

        payload: Optional[bytes] = None
        signature: Optional[bytes] = None
        for layer in signature_manifest.get("layers", []):
            if layer.get("mediaType") == _SIGNATURE_MEDIA_TYPE:
                payload = self._get_blob(registry, container, layer["digest"])
            annotation = layer.get("annotations", {}).get(
                _SIGNATURE_ANNOTATION
            )
            if annotation:
                signature = base64.b64decode(annotation)

        annotation = signature_manifest.get("annotations", {}).get(
            _SIGNATURE_ANNOTATION
        )
        if annotation:
            signature = base64.b64decode(annotation)
        if payload is None or signature is None:
            return False

        claims = json.loads(payload)
        claimed_digest = (
            claims.get("critical", {})
            .get("image", {})
            .get("docker-manifest-digest")
        )
        if claimed_digest != digest:
            return False
        return self._verify_signature(signature, payload)

    def _verify_bundle(self, bundle: bytes, image_digest: str) -> bool:
        document = json.loads(bundle)
        message_signature = document.get("messageSignature")
        if message_signature:
            return self._verify_message_signature(
                message_signature, image_digest
            )

        return self._verify_dsse_envelope(document, image_digest)

    def _verify_message_signature(
        self, message_signature: dict, image_digest: str
    ) -> bool:

        digest_bytes = bytes.fromhex(image_digest.split(":", 1)[1])
        expected_message_digest = base64.b64encode(
            hashlib.sha256(digest_bytes).digest()
        ).decode("ascii")
        if message_signature.get("messageDigest", {}).get("digest") != (
            expected_message_digest
        ):
            return False
        return self._verify_signature(
            base64.b64decode(message_signature["signature"]),
            digest_bytes,
            prehashed=True,
        )

    def _verify_dsse_envelope(self, document: dict, image_digest: str) -> bool:
        envelope = document.get("dsseEnvelope")
        if not envelope or len(envelope.get("signatures", [])) != 1:
            return False

        try:
            payload_type = envelope["payloadType"].encode("utf-8")
            payload = base64.b64decode(envelope["payload"], validate=True)
            signature = base64.b64decode(
                envelope["signatures"][0]["sig"], validate=True
            )
        except (KeyError, ValueError):
            return False

        pae = b" ".join(
            [
                b"DSSEv1",
                str(len(payload_type)).encode("ascii"),
                payload_type,
                str(len(payload)).encode("ascii"),
                payload,
            ]
        )
        if not self._verify_signature(signature, pae):
            return False

        try:
            statement = json.loads(payload)
            subjects = statement.get("subject", [])
            return any(
                subject.get("digest", {}).get("sha256")
                == image_digest.split(":", 1)[1]
                for subject in subjects
            )
        except (AttributeError, IndexError, json.JSONDecodeError):
            return False

    def _verify_signature(
        self, signature: bytes, payload: bytes, prehashed: bool = False
    ) -> bool:
        try:
            if isinstance(self._public_key, ec.EllipticCurvePublicKey):
                algorithm = hashes.SHA256()
                if prehashed:
                    from cryptography.hazmat.primitives.asymmetric.utils import (
                        Prehashed,
                    )

                    algorithm = Prehashed(algorithm)
                self._public_key.verify(
                    signature, payload, ec.ECDSA(algorithm)
                )
            elif isinstance(self._public_key, rsa.RSAPublicKey):
                self._public_key.verify(
                    signature, payload, PKCS1v15(), hashes.SHA256()
                )
            elif isinstance(
                self._public_key,
                (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey),
            ):
                self._public_key.verify(signature, payload)
            else:
                return False
            return True
        except (InvalidSignature, ValueError):
            return False

    def _get_manifest(
        self, registry: Any, container: Any, reference: str
    ) -> dict:
        response = registry.do_request(
            f"https://{container.manifest_url(reference)}",
            "GET",
            headers={
                "Accept": (
                    "application/vnd.oci.image.manifest.v1+json,"
                    "application/vnd.oci.image.index.v1+json"
                )
            },
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _get_blob(registry: Any, container: Any, digest: str) -> bytes:
        response = registry.get_blob(container, digest)
        response.raise_for_status()
        return response.content

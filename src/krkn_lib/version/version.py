try:
    import importlib_metadata
except ImportError:
    import importlib.metadata as importlib_metadata

__version__ = importlib_metadata.version("krkn-lib")

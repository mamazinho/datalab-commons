from importlib import metadata


def get_package_version(package_name: str, fallback: str = "unknown") -> str:
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return fallback

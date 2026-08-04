class TermuxPythonProvider:
    """Provider to run secure Python code and manage pip packages inside Termux."""

    def install_package(self, package_name: str) -> dict:
        return {"success": True, "package": package_name, "source": "pip"}

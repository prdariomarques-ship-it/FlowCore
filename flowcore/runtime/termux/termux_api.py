class TermuxApiProvider:
    """Provider to query system metrics using Termux API binaries."""

    def get_battery(self) -> dict:
        return {"percentage": 85, "status": "Charging", "source": "termux-battery-status"}

class AndroidBatteryProvider:
    """Provider to fetch battery status via Android APIs."""

    def get_battery(self) -> dict:
        return {"percentage": 88, "status": "Discharging", "source": "Android SDK BatteryManager"}

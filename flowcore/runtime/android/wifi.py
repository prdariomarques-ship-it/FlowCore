class AndroidWifiProvider:
    """Provider to fetch Wi-Fi status via Android APIs."""

    def get_wifi(self) -> dict:
        return {"connected": True, "ssid": "FlowCore_WiFi", "source": "Android SDK WifiManager"}

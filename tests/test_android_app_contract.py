from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android"


def test_android_app_targets_current_flowcore_api_contract():
    activity = (
        ANDROID
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "flowcore"
        / "android"
        / "MainActivity.kt"
    ).read_text(encoding="utf-8")
    build = (ANDROID / "app" / "build.gradle.kts").read_text(encoding="utf-8")

    assert 'FLOWCORE_BASE_URL' in activity
    assert 'buildConfigField("String", "FLOWCORE_BASE_URL"' in build
    assert '127.0.0.1:8080' in build
    assert '"/api/status"' in activity
    assert '"/api/system"' in activity
    assert '"/api/health"' in activity
    assert '"/api/passport"' in activity
    assert '127.0.0.1:8000' not in activity
    assert 'URL("$baseUrl$path")' in activity


def test_android_manifest_allows_api_network_and_uses_launcher_activity():
    manifest = (ANDROID / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
    network = (
        ANDROID
        / "app"
        / "src"
        / "main"
        / "res"
        / "xml"
        / "network_security_config.xml"
    ).read_text(encoding="utf-8")

    assert 'android.permission.INTERNET' in manifest
    assert 'android:networkSecurityConfig="@xml/network_security_config"' in manifest
    assert 'android:name=".MainActivity"' in manifest
    assert 'cleartextTrafficPermitted="true"' in network

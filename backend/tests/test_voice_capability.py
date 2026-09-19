from app.modules.voice.capability import local_voice_capability


def test_local_voice_is_explicitly_unavailable_without_provider() -> None:
    capability = local_voice_capability()
    assert capability.ready is False
    assert capability.input_state == "UNAVAILABLE"
    assert capability.output_state == "UNAVAILABLE"
    assert "文本" in capability.reason

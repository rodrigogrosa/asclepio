"""Configuração isolada para os testes da Fase 4: valores explícitos por teste (variável de ambiente
vence o .env), para não depender do .env da máquina (que pode ter chaves Azure reais) nem das
variáveis que o conftest do backend define quando as suítes rodam juntas."""

import pytest
from asclepio_multimodal.config import get_settings

ISOLATED_ENV = {
    "STT_PROVIDER": "auto",
    "TEXT_PROVIDER": "auto",
    "AUDIO_EVENTS_ENABLED": "true",
    "AZURE_SPEECH_KEY": "",
    "AZURE_SPEECH_REGION": "brazilsouth",
    "AZURE_LANGUAGE_KEY": "",
    "AZURE_LANGUAGE_ENDPOINT": "",
    "POSE_BACKEND": "openpose",
}


@pytest.fixture(autouse=True)
def _settings_isolados(monkeypatch):
    for k, v in ISOLATED_ENV.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

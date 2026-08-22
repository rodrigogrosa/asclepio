"""Autenticação real: sessões/refresh, MFA TOTP, troca de senha, gestão de usuários."""

import pyotp

API = "/api/v1"
PASSWORD = "Asclepio@2026"


def _login(client, email, password=PASSWORD):
    r = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def test_login_returns_refresh_and_session_fields(client):
    tok = (
        _login(client, "dr.marcos@asclepio.fiap")
        if False
        else _login(client, "enf.carla@asclepio.fiap")
    )
    assert tok["refresh_token"] and tok["refresh_expires_in"] > tok["expires_in"]
    assert tok["user"]["mfa_enabled"] is False and tok["user"]["is_demo"] is True


def test_refresh_rotation_and_reuse_detection(client):
    tok = _login(client, "enf.carla@asclepio.fiap")
    r1 = client.post(f"{API}/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r1.status_code == 200
    new_tok = r1.json()
    assert new_tok["refresh_token"] != tok["refresh_token"]
    # o access token antigo (sid rotacionado) deixa de valer
    assert (
        client.get(
            f"{API}/auth/me", headers={"Authorization": f"Bearer {tok['access_token']}"}
        ).status_code
        == 401
    )
    # reuso do refresh antigo → detecção → derruba todas as sessões (inclusive a nova)
    r2 = client.post(f"{API}/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r2.status_code == 401
    assert (
        client.get(
            f"{API}/auth/me", headers={"Authorization": f"Bearer {new_tok['access_token']}"}
        ).status_code
        == 401
    )


def test_logout_revokes_access_immediately(client):
    tok = _login(client, "enf.carla@asclepio.fiap")
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    assert client.get(f"{API}/auth/me", headers=h).status_code == 200
    assert client.post(
        f"{API}/auth/logout", json={"refresh_token": tok["refresh_token"]}, headers=h
    ).json()["ok"]
    assert client.get(f"{API}/auth/me", headers=h).status_code == 401


def test_sessions_list_and_revoke(client):
    t1 = _login(client, "enf.carla@asclepio.fiap")
    t2 = _login(client, "enf.carla@asclepio.fiap")
    h2 = {"Authorization": f"Bearer {t2['access_token']}"}
    sessions = client.get(f"{API}/auth/sessions", headers=h2).json()
    assert len(sessions) >= 2 and any(s["current"] for s in sessions)
    other = next(s for s in sessions if not s["current"])
    assert client.delete(f"{API}/auth/sessions/{other['id']}", headers=h2).json()["ok"]
    assert client.post(f"{API}/auth/logout-all", headers=h2).json()["ok"]
    assert (
        client.get(
            f"{API}/auth/me", headers={"Authorization": f"Bearer {t1['access_token']}"}
        ).status_code
        == 401
    )


def test_change_password_policy_and_effects(client):
    tok = _login(client, "dr.marcos@asclepio.fiap") if False else None
    # usa a enfermeira (médico Marcos está bloqueado por outro teste de lockout)
    tok = _login(client, "enf.carla@asclepio.fiap")
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    r = client.post(
        f"{API}/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "fraca"},
        headers=h,
    )
    assert r.status_code == 422
    r = client.post(
        f"{API}/auth/change-password",
        json={"current_password": "errada", "new_password": "Outra#Senha2026"},
        headers=h,
    )
    assert r.status_code == 400
    r = client.post(
        f"{API}/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "Outra#Senha2026"},
        headers=h,
    )
    assert r.status_code == 200
    # sessão atual continua válida; login com a nova senha funciona; volta para a senha demo
    assert client.get(f"{API}/auth/me", headers=h).status_code == 200
    tok2 = _login(client, "enf.carla@asclepio.fiap", "Outra#Senha2026")
    h2 = {"Authorization": f"Bearer {tok2['access_token']}"}
    assert (
        client.post(
            f"{API}/auth/change-password",
            json={"current_password": "Outra#Senha2026", "new_password": PASSWORD},
            headers=h2,
        ).status_code
        == 200
    )


def test_admin_real_flow_and_mfa_required(client, admin):
    me = client.get(f"{API}/auth/me", headers=admin).json()
    assert (
        me["role"] == "admin"
        and me["mfa_enabled"] is True
        and me["must_change_password"] is False
        and me["is_demo"] is False
    )
    # admin não pode desativar MFA
    r = client.post(
        f"{API}/auth/mfa/disable", json={"password": "x", "code": "000000"}, headers=admin
    )
    assert r.status_code == 403
    # rotas normais funcionam após onboarding
    assert client.get(f"{API}/dashboard/stats", headers=admin).status_code == 200


def test_mfa_wrong_code_and_recovery_code(client):
    # enfermagem ativa MFA, testa código errado e código de recuperação
    tok = _login(client, "enf.carla@asclepio.fiap")
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    setup = client.get(f"{API}/auth/mfa/setup", headers=h).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/") and "<svg" in setup["qr_svg"]
    assert (
        client.post(f"{API}/auth/mfa/enable", json={"code": "000000"}, headers=h).status_code == 400
    )
    codes = client.post(
        f"{API}/auth/mfa/enable", json={"code": pyotp.TOTP(setup["secret"]).now()}, headers=h
    ).json()["recovery_codes"]
    ch = _login(client, "enf.carla@asclepio.fiap")
    assert ch["mfa_required"] is True
    assert (
        client.post(
            f"{API}/auth/mfa/verify", json={"mfa_token": ch["mfa_token"], "code": "123456"}
        ).status_code
        == 401
    )
    r = client.post(f"{API}/auth/mfa/verify", json={"mfa_token": ch["mfa_token"], "code": codes[0]})
    assert r.status_code == 200
    h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # código de recuperação é de uso único
    ch2 = _login(client, "enf.carla@asclepio.fiap")
    assert (
        client.post(
            f"{API}/auth/mfa/verify", json={"mfa_token": ch2["mfa_token"], "code": codes[0]}
        ).status_code
        == 401
    )
    # enfermagem pode desativar MFA (não é admin)
    r = client.post(
        f"{API}/auth/mfa/disable",
        json={"password": PASSWORD, "code": pyotp.TOTP(setup["secret"]).now()},
        headers=h2,
    )
    assert r.status_code == 200, r.text
    assert "refresh_token" in _login(client, "enf.carla@asclepio.fiap")


def test_users_management(client, admin, medico):
    assert client.get(f"{API}/users", headers=medico).status_code == 403
    users = client.get(f"{API}/users", headers=admin).json()
    assert any(u["email"] == "rodrigo.grosa2011@gmail.com" and u["role"] == "admin" for u in users)
    specs = client.get(f"{API}/catalog/specialties", headers=admin).json()
    cardio = next(sp for sp in specs if sp["name"] == "Cardiologia")
    # médico sem CRM/especialidade → 422 ; CRM inválido → 422
    assert (
        client.post(
            f"{API}/users",
            json={"name": "Dr. Sem CRM", "email": "semcrm@asclepio.fiap", "role": "medico"},
            headers=admin,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{API}/users",
            json={
                "name": "Dr. CRM Ruim",
                "email": "crmruim@asclepio.fiap",
                "role": "medico",
                "crm": "abc",
                "specialty_id": cardio["id"],
            },
            headers=admin,
        ).status_code
        == 422
    )
    r = client.post(
        f"{API}/users",
        json={
            "name": "Dr. Teste Silva",
            "email": "dr.teste@asclepio.fiap",
            "role": "medico",
            "crm": "123456-SP",
            "specialty_id": cardio["id"],
        },
        headers=admin,
    )
    assert r.status_code == 201, r.text
    assert (
        r.json()["user"]["crm"] == "CRM 123456-SP"
        and r.json()["user"]["specialty_id"] == cardio["id"]
    )
    assert (
        client.get(f"{API}/users?role=medico&q=teste", headers=admin).json()[0]["email"]
        == "dr.teste@asclepio.fiap"
    )
    created, temp = r.json()["user"], r.json()["temporary_password"]
    assert created["must_change_password"] is True and temp
    # login do novo usuário com a senha temporária → 428 até trocar
    tok = _login(client, "dr.teste@asclepio.fiap", temp)
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    assert client.get(f"{API}/patients", headers=h).status_code == 428
    # duplicado → 409 ; atualizar papel ; reset de senha ; reset de MFA
    assert (
        client.post(
            f"{API}/users",
            json={
                "name": "Dup",
                "email": "dr.teste@asclepio.fiap",
                "role": "medico",
                "crm": "123456-SP",
                "specialty_id": cardio["id"],
            },
            headers=admin,
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"{API}/users/{created['id']}", json={"role": "enfermagem"}, headers=admin
        ).json()["role"]
        == "enfermagem"
    )
    assert client.post(f"{API}/users/{created['id']}/reset-password", headers=admin).json()[
        "temporary_password"
    ]
    assert client.post(f"{API}/users/{created['id']}/mfa/reset", headers=admin).json()["ok"]
    # admin não pode se rebaixar
    me = client.get(f"{API}/auth/me", headers=admin).json()
    assert (
        client.patch(f"{API}/users/{me['id']}", json={"role": "medico"}, headers=admin).status_code
        == 400
    )


def test_audit_has_auth_events(client, admin, auditor):
    actions = client.get(f"{API}/audit/actions", headers=auditor).json()
    for a in (
        "auth.mfa_enable",
        "auth.mfa_verify",
        "auth.refresh",
        "auth.refresh_reuse_detected",
        "auth.password_change",
        "user.create",
    ):
        assert a in actions, a

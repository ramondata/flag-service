"""
Testes unitários para o flag-service (app.py).

Como o app.py cria um pool de conexão real com o PostgreSQL e faz chamadas
HTTP reais ao auth-service assim que o módulo é importado, este arquivo:

  1. Define variáveis de ambiente obrigatórias ANTES do import.
  2. Faz "patch" de `psycopg2.pool.SimpleConnectionPool` para não tentar
     conectar em um banco real.
  3. Importa/recarrega o módulo `app` já com esses mocks no lugar.
  4. Faz "patch" de `app.requests.get` em cada teste para simular o
     auth-service (chave válida, inválida, timeout, indisponível etc).

Requisitos para rodar:
    pip install pytest pytest-mock

Executar com:
    pytest test_app.py -v
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib

# --- Variáveis de ambiente exigidas pelo app.py na importação ---
os.environ.setdefault("DATABASE_URL", "postgres://test:test@localhost:5432/testdb")
os.environ.setdefault("AUTH_SERVICE_URL", "http://auth-service-test:8001")


@pytest.fixture
def app_module():
    """
    Importa (ou recarrega) o módulo `app` com o SimpleConnectionPool
    mockado, para evitar conexão real com o PostgreSQL.
    """
    with patch("psycopg2.pool.SimpleConnectionPool") as mock_pool_cls:
        mock_pool_cls.return_value = MagicMock()

        if "app" in sys.modules:
            module = importlib.reload(sys.modules["app"])
        else:
            import app as module

        yield module


@pytest.fixture
def client(app_module):
    """Cliente de teste do Flask."""
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        yield test_client


@pytest.fixture
def mock_db_conn(app_module):
    """
    Mocka o par (conexão, cursor) retornado por pool.getconn(), permitindo
    configurar o retorno de fetchone/fetchall/rowcount em cada teste.
    """
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    app_module.pool.getconn.return_value = mock_conn
    return mock_conn, mock_cursor


def mock_auth_ok(app_module):
    """Ajuda a simular uma resposta 200 do auth-service."""
    response = MagicMock()
    response.status_code = 200
    return patch.object(app_module.requests, "get", return_value=response)


def mock_auth_invalid(app_module):
    """Ajuda a simular uma resposta 401 do auth-service (chave inválida)."""
    response = MagicMock()
    response.status_code = 401
    return patch.object(app_module.requests, "get", return_value=response)


# ----------------------------------------------------------------------
# /health
# ----------------------------------------------------------------------


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


# ----------------------------------------------------------------------
# Middleware de autenticação (require_auth)
# ----------------------------------------------------------------------


def test_flags_sem_header_authorization(client):
    response = client.get("/flags")
    assert response.status_code == 401
    assert "Authorization" in response.get_json()["error"]


def test_flags_com_chave_invalida(client, app_module):
    with mock_auth_invalid(app_module):
        response = client.get(
            "/flags", headers={"Authorization": "Bearer chave-invalida"}
        )
    assert response.status_code == 401
    assert response.get_json()["error"] == "Chave de API inválida"


def test_flags_auth_service_timeout(client, app_module):
    with patch.object(
        app_module.requests, "get", side_effect=requests_lib.exceptions.Timeout
    ):
        response = client.get("/flags", headers={"Authorization": "Bearer qualquer"})
    assert response.status_code == 504


def test_flags_auth_service_indisponivel(client, app_module):
    with patch.object(
        app_module.requests,
        "get",
        side_effect=requests_lib.exceptions.ConnectionError,
    ):
        response = client.get("/flags", headers={"Authorization": "Bearer qualquer"})
    assert response.status_code == 503


# ----------------------------------------------------------------------
# POST /flags (create_flag)
# ----------------------------------------------------------------------


def test_create_flag_sucesso(client, app_module, mock_db_conn):
    _, mock_cursor = mock_db_conn
    mock_cursor.fetchone.return_value = {
        "name": "nova-flag",
        "description": "desc",
        "is_enabled": True,
    }

    with mock_auth_ok(app_module):
        response = client.post(
            "/flags",
            json={"name": "nova-flag", "description": "desc", "is_enabled": True},
            headers={"Authorization": "Bearer chave-valida"},
        )

    assert response.status_code == 201
    assert response.get_json()["name"] == "nova-flag"


def test_create_flag_sem_name(client, app_module):
    with mock_auth_ok(app_module):
        response = client.post(
            "/flags",
            json={"description": "sem nome"},
            headers={"Authorization": "Bearer chave-valida"},
        )
    assert response.status_code == 400
    assert "name" in response.get_json()["error"]


def test_create_flag_duplicada(client, app_module, mock_db_conn):
    _, mock_cursor = mock_db_conn
    mock_cursor.execute.side_effect = app_module.psycopg2.IntegrityError()

    with mock_auth_ok(app_module):
        response = client.post(
            "/flags",
            json={"name": "flag-existente"},
            headers={"Authorization": "Bearer chave-valida"},
        )

    assert response.status_code == 409
    assert "já existe" in response.get_json()["error"]


# ----------------------------------------------------------------------
# GET /flags (get_flags) e GET /flags/<name> (get_flag)
# ----------------------------------------------------------------------


def test_get_flags_sucesso(client, app_module, mock_db_conn):
    _, mock_cursor = mock_db_conn
    mock_cursor.fetchall.return_value = [
        {"name": "flag-a", "is_enabled": True},
        {"name": "flag-b", "is_enabled": False},
    ]

    with mock_auth_ok(app_module):
        response = client.get(
            "/flags", headers={"Authorization": "Bearer chave-valida"}
        )

    assert response.status_code == 200
    assert len(response.get_json()) == 2


def test_get_flag_encontrada(client, app_module, mock_db_conn):
    _, mock_cursor = mock_db_conn
    mock_cursor.fetchone.return_value = {"name": "flag-a", "is_enabled": True}

    with mock_auth_ok(app_module):
        response = client.get(
            "/flags/flag-a", headers={"Authorization": "Bearer chave-valida"}
        )

    assert response.status_code == 200
    assert response.get_json()["name"] == "flag-a"


def test_get_flag_nao_encontrada(client, app_module, mock_db_conn):
    _, mock_cursor = mock_db_conn
    mock_cursor.fetchone.return_value = None

    with mock_auth_ok(app_module):
        response = client.get(
            "/flags/nao-existe", headers={"Authorization": "Bearer chave-valida"}
        )

    assert response.status_code == 404


# ----------------------------------------------------------------------
# PUT /flags/<name> (update_flag)
# ----------------------------------------------------------------------


def test_update_flag_sem_corpo(client, app_module):
    with mock_auth_ok(app_module):
        response = client.put(
            "/flags/flag-a",
            data="",
            content_type="application/json",
            headers={"Authorization": "Bearer chave-valida"},
        )
    assert response.status_code == 400


def test_update_flag_sem_campos_validos(client, app_module):
    with mock_auth_ok(app_module):
        response = client.put(
            "/flags/flag-a",
            json={"campo_invalido": "x"},
            headers={"Authorization": "Bearer chave-valida"},
        )
    assert response.status_code == 400
    assert "obrigatório" in response.get_json()["error"]


def test_update_flag_sucesso(client, app_module, mock_db_conn):
    _, mock_cursor = mock_db_conn
    mock_cursor.rowcount = 1
    mock_cursor.fetchone.return_value = {"name": "flag-a", "is_enabled": False}

    with mock_auth_ok(app_module):
        response = client.put(
            "/flags/flag-a",
            json={"is_enabled": False},
            headers={"Authorization": "Bearer chave-valida"},
        )

    assert response.status_code == 200
    assert response.get_json()["is_enabled"] is False


def test_update_flag_nao_encontrada(client, app_module, mock_db_conn):
    _, mock_cursor = mock_db_conn
    mock_cursor.rowcount = 0

    with mock_auth_ok(app_module):
        response = client.put(
            "/flags/nao-existe",
            json={"is_enabled": True},
            headers={"Authorization": "Bearer chave-valida"},
        )

    assert response.status_code == 404


# ----------------------------------------------------------------------
# DELETE /flags/<name> (delete_flag)
# ----------------------------------------------------------------------


def test_delete_flag_sucesso(client, app_module, mock_db_conn):
    _, mock_cursor = mock_db_conn
    mock_cursor.rowcount = 1

    with mock_auth_ok(app_module):
        response = client.delete(
            "/flags/flag-a", headers={"Authorization": "Bearer chave-valida"}
        )

    assert response.status_code == 204


def test_delete_flag_nao_encontrada(client, app_module, mock_db_conn):
    _, mock_cursor = mock_db_conn
    mock_cursor.rowcount = 0

    with mock_auth_ok(app_module):
        response = client.delete(
            "/flags/nao-existe", headers={"Authorization": "Bearer chave-valida"}
        )

    assert response.status_code == 404

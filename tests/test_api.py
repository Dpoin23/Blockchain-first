"""HTTP mutations require a custom header, and optionally a bearer token."""

import json

import pytest

from chain.blockchain import Blockchain
from chain.constants import BLOCK_REWARD
from chain.node import bind_is_allowed, create_app
from chain.wallet import Wallet

HEADER = {"X-Chain-Request": "1"}


@pytest.fixture
def node(tmp_path):
    app = create_app(blockchain=Blockchain(difficulty=1), data_dir=tmp_path)
    return app


@pytest.fixture
def client(node):
    return node.test_client()


def test_bind_policy():
    assert bind_is_allowed("127.0.0.1", "") is True
    assert bind_is_allowed("0.0.0.0", "") is False
    assert bind_is_allowed("0.0.0.0", "secret") is True


def test_mine_requires_the_custom_header(client):
    rejected = client.post("/mine")
    assert rejected.status_code == 400
    assert client.get("/chain").get_json()["length"] == 1

    mined = client.post("/mine", headers=HEADER)
    assert mined.status_code == 200
    body = mined.get_json()
    assert body["index"] == 1
    assert body["hash"]
    assert client.get("/chain").get_json()["length"] == 2


def test_public_reads_do_not_include_the_node_key(client, node):
    secret = node.extensions["chain_wallet"]._private_key.private_bytes_raw().hex()
    info = client.get("/node").get_json()
    assert set(info) == {"address"}
    assert secret not in json.dumps(info)
    assert secret not in client.get("/chain").get_data(as_text=True)


def test_transfer_is_mined_into_the_recipient_balance(client, node):
    miner = node.extensions["chain_wallet"]
    assert client.post("/mine", headers=HEADER).status_code == 200
    recipient = Wallet.generate()
    tx = miner.sign_transaction(recipient=recipient.address, amount=5, fee=1, nonce=0)
    queued = client.post("/transactions/new", json=tx, headers=HEADER)
    assert queued.status_code == 201
    assert client.post("/mine", headers=HEADER).status_code == 200

    assert client.get(f"/account/{recipient.address}").get_json()["balance"] == 5
    miner_account = client.get(f"/account/{miner.address}").get_json()
    assert miner_account["balance"] == 2 * BLOCK_REWARD - 5
    assert miner_account["nonce"] == 1


def test_overspend_and_bad_content_type_are_400(client, node):
    miner = node.extensions["chain_wallet"]
    assert client.post("/mine", headers=HEADER).status_code == 200
    tx = miner.sign_transaction(
        recipient=Wallet.generate().address,
        amount=10_000,
        fee=0,
        nonce=0,
    )
    rejected = client.post("/transactions/new", json=tx, headers=HEADER)
    assert rejected.status_code == 400
    plain = client.post(
        "/transactions/new",
        data="{}",
        headers={**HEADER, "Content-Type": "text/plain"},
    )
    assert plain.status_code == 400


def test_bearer_token_gates_mutations_only(tmp_path):
    app = create_app(
        blockchain=Blockchain(difficulty=1),
        data_dir=tmp_path,
        api_token="secret",
    )
    client = app.test_client()
    assert client.get("/chain").status_code == 200
    assert client.post("/mine", headers=HEADER).status_code == 401
    assert client.post("/mine", headers={**HEADER, "Authorization": "Bearer no"}).status_code == 401
    mined = client.post("/mine", headers={**HEADER, "Authorization": "Bearer secret"})
    assert mined.status_code == 200


def test_metadata_peer_is_rejected(client):
    response = client.post(
        "/nodes/register",
        json={"nodes": ["http://169.254.169.254:80"]},
        headers=HEADER,
    )
    assert response.status_code == 400
    assert client.get("/nodes").get_json()["length"] == 0


def test_resolve_without_peers_keeps_the_local_chain(client):
    response = client.post("/nodes/resolve", headers=HEADER)
    body = response.get_json()
    assert response.status_code == 200
    assert body["replaced"] is False
    assert body["length"] == 1

from __future__ import annotations

import httpx
import pytest

from conftest import ReseauInterdit


def test_aucun_appel_reseau():
    with pytest.raises(ReseauInterdit):
        httpx.get("https://exemple.test/")
    with pytest.raises(ReseauInterdit):
        with httpx.Client() as c:
            c.post("https://exemple.test/", json={})

    simule = httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": True}))
    with httpx.Client(transport=simule) as c:
        assert c.get("https://exemple.test/").json() == {"ok": True}

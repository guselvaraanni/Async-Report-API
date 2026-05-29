def test_legacy_generate_and_status_shape(client):
    gen = client.post("/reports/generate", json={"user_id": 1, "rows": 5})
    assert gen.status_code == 202
    payload = gen.get_json()
    assert "task_id" in payload

    tid = payload["task_id"]
    st = client.get(f"/reports/status/{tid}")
    assert st.status_code == 200
    sdata = st.get_json()
    # Keep legacy-critical fields present for UI/backward compat
    assert sdata["task_id"] == tid
    assert "status" in sdata
    assert "rows_processed" in sdata


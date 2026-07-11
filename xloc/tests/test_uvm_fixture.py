def test_uvm_report_server_emits_stable_location_ids(xverif_fixture) -> None:
    log = (
        xverif_fixture("xloc.uvm") / "out/sim.log"
    ).read_text(encoding="utf-8", errors="replace")
    assert "UVM_INFO L_00000001" in log
    assert "UVM_ERROR L_00000002" in log
    assert "[FILE_OPEN] cannot open config file" in log
    assert "[PKT_MISMATCH] expected=8'hFF actual=8'hFE" in log
    assert "UVM_WARNING L_" in log
    assert "V C S   S i m u l a t i o n   R e p o r t" in log

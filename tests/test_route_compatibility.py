from its_signal_control.utils import route_file_matches_network


def test_route_file_matches_network_when_all_edges_exist(tmp_path) -> None:
    network_file = tmp_path / "map.net.xml"
    route_file = tmp_path / "map.rou.xml"
    network_file.write_text(
        '<net><edge id="a"/><edge id="b"/><edge id=":internal" function="internal"/></net>',
        encoding="utf-8",
    )
    route_file.write_text(
        '<routes><vehicle id="0"><route edges="a b"/></vehicle></routes>',
        encoding="utf-8",
    )

    assert route_file_matches_network(str(route_file), str(network_file)) is True


def test_route_file_does_not_match_network_when_edge_is_missing(tmp_path) -> None:
    network_file = tmp_path / "map.net.xml"
    route_file = tmp_path / "map.rou.xml"
    network_file.write_text('<net><edge id="a"/></net>', encoding="utf-8")
    route_file.write_text(
        '<routes><vehicle id="0"><route edges="a removed-edge"/></vehicle></routes>',
        encoding="utf-8",
    )

    assert route_file_matches_network(str(route_file), str(network_file)) is False


def test_route_file_does_not_match_network_when_xml_is_invalid(tmp_path) -> None:
    network_file = tmp_path / "map.net.xml"
    route_file = tmp_path / "map.rou.xml"
    network_file.write_text('<net><edge id="a"/></net>', encoding="utf-8")
    route_file.write_text("<routes>", encoding="utf-8")

    assert route_file_matches_network(str(route_file), str(network_file)) is False

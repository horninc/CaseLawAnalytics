from rechtspraak_query_app.parser import parser
from lxml import etree
from rdflib.namespace import DCTERMS


def test_parse_element():
    element = etree.ElementTree().parse("test/test_ecli.xml")
    graph = parser.parse_xml_element(element, "ECLI:NL:HR:1999:AA3837")
    references = list(graph.subject_objects(DCTERMS.references))
    assert len(references)==3
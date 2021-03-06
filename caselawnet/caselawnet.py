"""
This module forms the main interface to the functionalities of caselawnet.
"""
import warnings
from . import search, network_analysis, enrich, utils, lido_parser

def search_keyword(keyword, **args):
    """
    Search the rechtspraak.nl api for this keyword.
    It returns a list of nodes, where each node represents one case.
    The nodes contain at least the field 'ecli' for ECLI identifier
    and the field 'id' for URI identifier.

    :param keyword: keyword to search for
    :param args: search parameters
    :return: list of rich nodes
    """
    nodes = search.search(keyword, **args)
    return nodes


def enrich_eclis(eclis, rootpath=None, db_session=None):
    """
    Retrieves meta information for the proviced ECLI identifiers.
    If there is no meta information found, empty fields are provided.

    :param eclis: list of ECLI identifiers
    :param rootpath: directory containing data
    :param db: database connection
    :return: list of rich nodes.
    """
    nodes = enrich.get_meta_data(eclis, rootpath=rootpath, db_session=db_session)

    return nodes


def retrieve_links(eclis, auth=None, nr_degrees=0):
    """
    Retrieve references between cased from the LiDO api (http://linkeddata.overheid.nl)
    If the nodes are not yet rich (so: only ecli number),
     the metadata is retrieved as well.
    :param eclis: a list of ECLI codes
    :param auth: dict with 'username' and 'password' for the LiDO api
    :param nr_degrees: Nodes that are `nr_degrees` away in network are also retrieved
    :return: list of rich links
    """
    warnings.warn('The LiDO link API is not completely functional yet!', Warning)
    links_df, articles = lido_parser.get_links_articles(eclis, auth=auth, nr_degrees=nr_degrees)
    links = links_df.to_dict(orient='records')
    links_rich = enrich_links(links)
    # TODO: use the articles
    return links_rich


def get_network(nodes, links):
    """
    Add network information

    :param nodes: List of nodes
    :param links: List of links
    :return: nodes, links: nodes has network information
    """
    nodes = network_analysis.add_network_statistics(nodes, links)
    return nodes, links


def enrich_links(links):
    """
    Makes a list of link dictionaries suitable for network.

    :param links: list of dict with at least 'source' and 'target',
        that should contain ECLI identifiers
    :return: list of dict with links
    """
    return enrich.enrich_links(links)

def links_to_network(links, rootpath=None, db_session=None):
    """
    Creates nodes and links of a network from a list with dictionaries
    that contain 'source' and 'target' attributes of known links

    :param links: list of dict with at least 'source' and 'target'
    :param db_session: sqlalchemy database session
    :return: nodes, links_out: network with these links
    """
    eclis = list(set([l['source'] for l in links] +
                     [l['target'] for l in links]))
    nodes = enrich_eclis(eclis, rootpath=rootpath, db_session=db_session)

    links = enrich_links(links)

    nodes, links_out = get_network(nodes, links)
    return nodes, links_out


import caselawnet
import traceback
import json
import io
from flask import Flask, request, render_template, make_response, g, send_from_directory
import pandas as pd
import random
import os
from caselawnet import dbutils
app = Flask(__name__)


ALLOWED_EXTENSIONS = set(['json', 'csv'])
app.config.from_pyfile('settings.cfg')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        if app.config['DBPATH'] is not None:
            db = g._database = dbutils.get_session(app.config['DBPATH'])
    return db
    
    
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route('/')
def index():
    return render_template('index.html', version=caselawnet.__version__)


@app.route('/eclis')
def eclis():
    return render_template('eclis.html')


@app.route('/query_eclis', methods=['POST'])
def query_eclis():
    try:
        nodes_file = None
        links_file = None
        network_file = None
        warning = None
        if('eclis' in request.form):
            eclis_csv = request.form['eclis']
            title = request.form.get('title', 'Network')
            include_links = int(request.form.get('include_linked', [0])[0])
            eclis = [e.strip() for e in eclis_csv.splitlines()]
            eclis = [e for e in eclis if len(e)>0]
            links = caselawnet.retrieve_links(eclis,
                                              auth={'username': app.config['LIDO_USERNAME'],
                                                        'password': app.config['LIDO_PASSWD']},
                                              nr_degrees=include_links)
            if include_links > 0:
                eclis += [caselawnet.utils.url_to_ecli(link['source'])
                         for link in links]
                eclis += [caselawnet.utils.url_to_ecli(link['target'])
                          for link in links]
                eclis = set(eclis)
            nodes = caselawnet.enrich_eclis(eclis,  db_session=get_db())
            nodes, links = caselawnet.get_network(nodes, links)

            nodes_csv = caselawnet.to_csv(nodes)
            nodes_file = save_result(nodes_csv, 'csv')
            links_csv = pd.DataFrame(links).to_csv(index=False)
            links_file = save_result(links_csv, 'csv')
            network_json = caselawnet.to_sigma_json(nodes, links, title)
            network_file = save_result(network_json, 'json')
            warning = 'The link extractor is not functional yet, the links will be incomplete.'
            if len(links) == 0:
                warning += '\nNo links were found!'
        return render_template("eclis.html",
                               network_file=network_file,
                               nodes_file=nodes_file,
                               links_file=links_file,
                               warning=warning)
    except caselawnet.utils.InvalidECLIError as error:
        return render_template("eclis.html",
                               error="Invalid ecli: "+str(error))
    except Exception as error:
        print(error)
        traceback.print_exc()
        return render_template("links.html",
                               error="Sorry, something went wrong!")

@app.route('/links')
def links():
    return render_template('links.html')


def read_csv(path, sep=',', header='infer'):
    links_df = pd.read_csv(path, sep=sep, header=header)
    links_df.columns = ['source', 'target']
    # Strip leading or trailing whitespace
    links_df.source = links_df.source.str.strip()
    links_df.target = links_df.target.str.strip()
    links_df = links_df.drop_duplicates()
    eclis = list(pd.concat([links_df['source'], links_df['target']]).unique())
    return links_df, eclis

def save_result(data, extension):
    name = '%030x' % random.randrange(16 ** 30) + '.' + extension
    with open(os.path.join(app.config['UPLOAD_FOLDER'], name), 'w', encoding='utf-8') as fn:
        fn.write(data)
    return name

@app.route('/query_links', methods=['POST'])
def query_links():
    try:
        nodes_file = None
        links_file = None
        network_file = None
        warning = None
        if('links' in request.form):
            links_csv = request.form['links']
            title = request.form.get('title', 'Network')
            links_df, eclis = read_csv(io.StringIO(links_csv),
                                                     sep=',', header=None)
            links_dict = links_df.to_dict(orient='records')
            nodes, links = caselawnet.links_to_network(links_dict, db_session=get_db())
            if len(nodes) < len(eclis):
                existing_eclis = [node['ecli'] for node in nodes]
                difference = set(eclis) - set(existing_eclis)
                warning = "The following ECLI cases were not found: " + \
                    str(difference)
            if len(nodes) == 0:
                return render_template("links.html",
                                       error="No resulting matches!")
            nodes_csv = caselawnet.to_csv(nodes)
            nodes_file = save_result(nodes_csv, 'csv')
            links_csv = pd.DataFrame(links).to_csv(index=False)
            links_file = save_result(links_csv, 'csv')
            network_json = caselawnet.to_sigma_json(nodes, links, title)
            network_file = save_result(network_json, 'json')
        return render_template("links.html",
                               network_file=network_file,
                               nodes_file=nodes_file,
                               links_file=links_file,
                               warning=warning)
    except caselawnet.utils.InvalidECLIError as error:
        return render_template("links.html",
                               error="Invalid ecli: "+str(error))
    except Exception as error:
        print(error)
        traceback.print_exc()
        return render_template("links.html",
                               error="Sorry, something went wrong!")

@app.route('/downloads/<filename>_<filename_out>')
def download_file(filename, filename_out):
    if filename_out is None:
        fn, ext = os.path.splitext(filename)
        filename_out = 'network' + ext
    return send_from_directory(app.config['UPLOAD_FOLDER'],
                               filename,
                               as_attachment=True,
                               attachment_filename=filename_out)



def get_parameter_values():
    values = getattr(g, '_values', None)
    if values is None:
        with open('static/values.json') as f:
            values = json.load(f)
        g._values = values
    return values

@app.route('/search/')
def search():
    values = get_parameter_values()
    return render_template('search.html',
                           values=values)

@app.route('/search_query/', methods=['POST'])
def search_query():
    nodes_file = None
    links_file = None
    network_file = None
    nr_results = None
    warning = None
    values = get_parameter_values()

    try:
        form = {k.lower(): request.form.getlist(k) for k in request.form.keys()}
        kw = form.pop('keyword', '')[0]
        if kw is not '':
            include_links = int(form.pop('include_linked', [0])[0])
            nodes = caselawnet.search_keyword(kw, **form)
            nr_results = len(nodes)
            if nr_results > 0:
                links = caselawnet.retrieve_links([n['ecli'] for n in nodes],
                                                  auth={'username': app.config['LIDO_USERNAME'],
                                                        'password': app.config['LIDO_PASSWD']},
                                                  nr_degrees=include_links)
                # Add the new nodes:
                if include_links > 0:
                    eclis = [caselawnet.utils.url_to_ecli(link['source'])
                             for link in links]
                    eclis += [caselawnet.utils.url_to_ecli(link['target'])
                             for link in links]
                    eclis = set(eclis)
                    eclis = [e for e in eclis if e not in
                             [n['ecli'] for n in nodes]]
                    nodes += caselawnet.enrich_eclis(eclis, db_session=get_db())
                    nr_results = len(nodes)
                nodes, links = caselawnet.get_network(nodes, links)
                nodes_csv = caselawnet.to_csv(nodes)
                nodes_file = save_result(nodes_csv, 'csv')
                links_csv = pd.DataFrame(links).to_csv(index=False)
                links_file = save_result(links_csv, 'csv')
                network_json = caselawnet.to_sigma_json(nodes, links, kw)
                network_file = save_result(network_json, 'json')
                warning = 'The link extractor is not functional yet, the links will be incomplete.'
                if len(links) == 0:
                    warning += '\nNo links were found!'
        else:
            warning = 'Keyword field is empty!'
        return render_template('search.html',
                               values=values,
                               nodes_file=nodes_file,
                               links_file=links_file,
                               network_file= network_file,
                               nr_results=nr_results,
                               warning=warning)
    except Exception as error:
        print(error)
        traceback.print_exc()
        return render_template("search.html",
                               values=values,
                               error="Sorry, something went wrong!")
    
if __name__ == '__main__':
    app.run(debug=True)

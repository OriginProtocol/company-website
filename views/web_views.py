from collections import OrderedDict
from datetime import datetime
import os

from app import app
from database import db, db_models

from config import constants, universal, partner_details
from flask import (jsonify, redirect, render_template,
                   request, flash, g, url_for, Response,
                   stream_with_context, session)
from flask_babel import gettext, Babel, Locale
from util.recaptcha import ReCaptcha
from logic.emails import mailing_list
import requests

from util.misc import sort_language_constants, get_real_ip, concat_asset_files

import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery

# Translation: change path of messages.mo files
app.config['BABEL_TRANSLATION_DIRECTORIES'] = '../translations'
babel = Babel(app)

recaptcha = ReCaptcha(app=app)
if not recaptcha.is_enabled:
    print("Warning: recaptcha is not is_enabled")

@app.before_request
def beforeRequest():
    """ Processing of URL before any routing """
    # Force https on prod
    if constants.HTTPS:
        if not request.url.startswith('https'):
            return redirect(request.url.replace('http', 'https', 1))

    selected_lang = None
    if request.view_args and 'lang_code' in request.view_args:
        selected_lang = request.view_args.pop('lang_code')
    elif request.args and 'lang_code' in request.args:
        selected_lang = request.args['lang_code']

    if selected_lang in constants.LANGUAGES:
        g.current_lang = selected_lang
    else:
        # Use Accept-Languages header for fallback
        g.current_lang = get_locale()

@app.route('/')
def root():
    return render_template('index.html')

@app.route('/robots.txt')
def robots():
    return app.send_static_file('files/robots.txt')

@app.route('/apple-app-site-association')
def apple_app_site_association():
    return app.send_static_file('files/apple-app-site-association.json')

@app.route('/mobile/<link_code>')
@app.route('/mobile')
def mobile(link_code=None):
    role = request.args.get('role')
    return render_template('mobile.html', link_code=link_code, role=role, ios_url=universal.IOS_URL, android_url=universal.ANDROID_URL)

@app.route('/<lang_code>')
def index():
    return render_template('index.html')

@app.route('/team')
@app.route('/<lang_code>/team')
def team():
    # fetch our list of contributors from the DB
    contributors = db_models.Contributor.query.all()

    # manually add aure until he gets his first PR in
    aure = db_models.Contributor()
    aure.username = 'auregimon'
    aure.avatar = 'https://avatars1.githubusercontent.com/u/13142288?s=460&v=4'

    # community team
    community = [{'avatar':'kath', 'url': 'https://twitter.com/kath1213', 'name':'Kath Brandon' },
                 # {'avatar':'dave', 'url': 'https://twitter.com/davecraige', 'name':'Dave Craig'},
                 # {'avatar':'andrei','url': 'https://www.linkedin.com/in/andreicosminmunteanu/', 'name':'Andrei Munteanu'},
                 # {'avatar':'mijbel', 'url': 'https://twitter.com/mijbelf', 'name':'Mijbel AlQattan' },
                 # {'avatar':'adam', 'url': 'https://www.linkedin.com/in/adamcalihman/', 'name':'Adam Calihman' },
                 # {'avatar':'russell', 'url': 'https://twitter.com/_russellduncan_', 'name':'Russell Duncan' },
                 {'avatar':'elaine', 'url': 'https://www.linkedin.com/in/yingyin1225/', 'name':'Elaine Yin' },
                 {'avatar':'zaurbek', 'url': 'https://vk.com/zaurbeksf', 'name':'Zaurbek Ivanov' },
                 {'avatar':'bonnie', 'url': 'https://www.linkedin.com/in/bonnie-yen-35025b16b', 'name':'Bonnie Yen' },
                 {'avatar':'jenny', 'url': 'https://www.linkedin.com/in/jenny-wang-a15ba32b/', 'name':'Jenny Wang' }]
    return render_template('team.html', contributors=[aure] + contributors, community=community)



@app.route('/presale')
@app.route('/<lang_code>/presale')
def presale():
    return redirect('/tokens', code=302)

@app.route('/tokens')
@app.route('/<lang_code>/tokens')
def tokens():
    return render_template('tokens.html')

@app.route('/whitepaper')
@app.route('/<lang_code>/whitepaper')
def whitepaper():
    localized_filename = 'whitepaper_v5_%s.pdf' % g.current_lang.lower()
    whitepaper_path = (os.path.join(app.root_path, '..', 'static', 'docs', localized_filename))
    if os.path.isfile(whitepaper_path):
        return app.send_static_file('docs/%s' % localized_filename)
    else:
        # Default to English
        return app.send_static_file('docs/whitepaper_v5.pdf')

@app.route('/product-brief')
@app.route('/<lang_code>/product-brief')
def product_brief():
    localized_filename = 'product_brief_v17_%s.pdf' % g.current_lang.lower()
    product_brief_path = (os.path.join(app.root_path, '..', 'static', 'docs', localized_filename))
    if os.path.isfile(product_brief_path):
        return app.send_static_file('docs/%s' % localized_filename)
    else:
        # Default to English
        return app.send_static_file('docs/product_brief_v17.pdf')

@app.route('/mailing-list/join', methods=['POST'])
def join_mailing_list():
    if 'email' in request.form:
        email = request.form['email']
        dapp_user = request.form['dapp_user'] if 'dapp_user' in request.form else None
        ip_addr = get_real_ip()
        feedback = mailing_list.send_welcome(email, ip_addr)
        mailing_list.add_sendgrid_contact(email=email, dapp_user=dapp_user)
        return jsonify(feedback)
    else:
        return jsonify("Missing email")

@app.route('/vk577', methods=['GET'])
def vk577():
    return jsonify('Temporaily posting as requested for claiming @originprotocol on vk.com: VK577')

@app.route('/presale/join', methods=['POST'])
def join_presale():
    full_name = request.form['full_name']
    email = request.form['email']
    accredited = request.form["accredited"]
    entity_type = request.form["entity_type"]
    desired_allocation = request.form["desired_allocation"]
    desired_allocation_currency = request.form["desired_allocation_currency"]
    citizenship = request.form["citizenship"]
    sending_addr = request.form["sending_addr"]
    note = request.form["note"]
    ip_addr = get_real_ip()
    print("CHECK:", email, request.remote_addr) # Temp until we get IP recorded
    if not full_name:
        return jsonify(gettext("Please enter your name"))
    if not email:
        return jsonify(gettext("Please enter your email"))
    if not accredited or not entity_type or not citizenship or not desired_allocation_currency:
        return jsonify(gettext("An error occured"))
    if not desired_allocation:
        return jsonify(gettext("Please enter your desired allocation"))
    if "confirm" not in request.form:
        return jsonify(gettext("Please agree to the important notice"))
    if not recaptcha.verify():
        return jsonify(gettext("Please prove you are not a robot."))
    feedback = mailing_list.presale(full_name, email, accredited, entity_type, desired_allocation, desired_allocation_currency, citizenship, sending_addr, note, request.remote_addr)
    mailing_list.add_sendgrid_contact(email, full_name, citizenship)
    flash(feedback)
    return jsonify("OK")

@app.route('/mailing-list/unsubscribe', methods=['GET'])
def unsubscribe():
    email = request.args.get("email")
    feedback = mailing_list.unsubscribe(email)
    mailing_list.unsubscribe_sendgrid_contact(email)
    flash(feedback)
    return redirect('/', code=302)

@app.route('/webhook/fullcontact', methods=['GET','POST'])
def fullcontact_webhook():
    print('POSTED!!')
    print(request.get_json())
    print(request.json)
    return redirect('/', code=302)

@app.route('/build-on-origin')
@app.route('/<lang_code>/build-on-origin')
def build_on_origin():
    return redirect(url_for('partners', lang_code=g.current_lang), code=301)

@app.route('/developers')
@app.route('/<lang_code>/developers')
def developers():
    return render_template('developers.html')

@app.route('/discord')
@app.route('/<lang_code>/discord')
def discord():
    return redirect(universal.DISCORD_URL, code=301)

@app.route('/ios')
@app.route('/<lang_code>/ios')
def ios():
    return redirect(universal.IOS_URL, code=301)

@app.route('/android')
@app.route('/<lang_code>/android')
def android():
    return redirect(universal.ANDROID_URL, code=301)

@app.route('/telegram')
@app.route('/<lang_code>/telegram')
def telegram():
    return redirect(universal.TELEGRAM_URL, code=301)

@app.route('/partners')
@app.route('/<lang_code>/partners')
def partners():
    return render_template('partners.html')

@app.route('/privacy')
@app.route('/<lang_code>/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/tos')
@app.route('/<lang_code>/tos')
def tos():
    return render_template('tos.html')

@app.route('/aup')
@app.route('/<lang_code>/aup')
def aup():
    return render_template('aup.html')

@app.route('/creator')
@app.route('/<lang_code>/creator')
def creator():
    return render_template('creator.html')

@app.route('/partners/interest', methods=['POST'])
def partners_interest():
    name = request.form['name']
    company_name = request.form['company_name']
    email = request.form['email']
    website = request.form["website"]
    note = request.form["note"]
    ip_addr = get_real_ip()
    if not name:
        return jsonify(gettext("Please enter your name"))
    if not company_name:
        return jsonify(gettext("Please enter your company name"))
    if not email:
        return jsonify(gettext("Please enter your email"))
    if not recaptcha.verify():
        return jsonify(gettext("Please prove you are not a robot."))
    feedback = mailing_list.partners_interest(name, company_name, email,
                                              website, note, ip_addr)
    mailing_list.add_sendgrid_contact(email,name)
    flash(feedback)
    return jsonify("OK")

@app.route('/static/css/all_styles.css')
def assets_all_styles():
    return Response(concat_asset_files([
        "static/css/vendor-bootstrap-4.0.0-beta2.css",
        "static/css/style.css",
        "static/css/alertify.css",
        "static/css/animate.css"
    ]), mimetype="text/css")

@app.route('/static/js/all_javascript.js')
def assets_all_javascript():
    return Response(concat_asset_files([
        "static/js/vendor-jquery-3.2.1.min.js",
        "static/js/vendor-popper.min.js",
        "static/js/vendor-bootstrap.min.js",
        "static/js/vendor-alertify.js",
        "static/js/vendor-d3.min.js",
        "static/js/vendor-wow.min.js",
        "static/js/script.js"
    ]), mimetype="application/javascript")

@app.route('/origin-js/origin-v<version>.js', methods=['GET'])
def serve_origin_js(version):

    # temporary hack
    # should really do this w/ NGINX or serve from a proper CDN

    # serves up:
    # https://github.com/OriginProtocol/origin-js/releases/download/v0.5.10/origin.js
    # when you visit:
    # https://code.originprotocol.com/origin-js/origin-v0.5.10.js

    url = "https://github.com/OriginProtocol/origin-js/releases/download/v%s/origin.js" % version
    req = requests.get(url, stream=True)
    return Response(stream_with_context(req.iter_content(chunk_size=2048)), content_type="text/javascript")

YOUTUBE_CONFIG = {
  "web":
  {
    "client_id": constants.YOUTUBE_CLIENT_ID,
    "project_id": constants.YOUTUBE_PROJECT_ID,
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://www.googleapis.com/oauth2/v3/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": constants.YOUTUBE_CLIENT_SECRET,
    "redirect_uris":[constants.YOUTUBE_REDIRECT_URL]
  }
}

SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']

@app.route('/youtube')
def youtube():
  if not (constants.YOUTUBE_TOKEN and constants.YOUTUBE_REFRESH_TOKEN):
    return redirect('/youtube/authorize')

  return redirect(url_for('index', lang_code=get_locale()))

@app.route('/youtube/authorize')
def authorize():
  flow = google_auth_oauthlib.flow.Flow.from_client_config(
      client_config=YOUTUBE_CONFIG, scopes=SCOPES)
  flow.redirect_uri = url_for('oauth2callback', _external=True)
  authorization_url, state = flow.authorization_url(
      access_type='offline',
      include_granted_scopes='true')

  session['state'] = state

  return redirect(authorization_url)


@app.route('/youtube/oauth2callback')
def oauth2callback():
  state = session['state']
  flow = google_auth_oauthlib.flow.Flow.from_client_config(
      client_config=YOUTUBE_CONFIG, scopes=SCOPES, state=state)
  flow.redirect_uri = url_for('oauth2callback', _external=True)

  authorization_response = request.url
  flow.fetch_token(authorization_response=authorization_response)

  #save the token and refresh_token in the credentials as environment variables
  credentials = flow.credentials

  print("YOUTUBE TOKEN", credentials.token)
  print("YOUTUBE REFRESH_TOKEN", credentials.refresh_token)

  return redirect(url_for('index', lang_code=get_locale()))

def get_channel_info(client, **kwargs):
  response = client.channels().list(**kwargs).execute()

  statistics = response['items'][0]['statistics']
  updated_count = statistics['subscriberCount'].encode('ascii')
  print("Updating stats for Youtube: " + str(updated_count))

  stat = db_models.SocialStat()
  stat.name = 'Youtube'
  stat.subscribed_count = updated_count
  db.session.add(stat)
  db.session.commit()

  return redirect(url_for('index', lang_code=get_locale()))

@app.context_processor
def inject_partners():
    return dict(partners_dict = partner_details.PARTNERS)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@babel.localeselector
def get_locale():
    browser_language = request.accept_languages.best_match(constants.LANGUAGES) or 'en'
    return g.get('current_lang', browser_language)

@app.context_processor
def inject():
    return {'now': datetime.utcnow(), 'universal':universal}

@app.context_processor
def inject_conf_var():
    current_language = get_locale()
    try:
        current_language_direction = Locale(current_language).text_direction
    except:
        current_language_direction = 'ltr'
    try:
        available_languages =\
            OrderedDict([(lang,
                          Locale(lang).get_language_name(lang).capitalize())
                         for lang in sort_language_constants()])
    except:
        available_languages = {'en': "English"}
    return dict(
        CURRENT_LANGUAGE=current_language,
        CURRENT_LANGUAGE_DIRECTION=current_language_direction,
        AVAILABLE_LANGUAGES=available_languages,
        DOMAIN=request.headers['Host'])

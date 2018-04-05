import logging
import time
import flask
from flask import current_app
from oic.oic import Client
from oic.oic.message import AuthorizationResponse
from werkzeug.utils import redirect
logger = logging.getLogger(__name__)

def my_handle_authentication_response(self):
    # parse authentication response
    query_string = flask.request.query_string.decode('utf-8')
    authn_resp = self.client.parse_response(AuthorizationResponse, info=query_string, sformat='urlencoded')
    logger.debug('received authentication response: %s', authn_resp.to_json())

    if authn_resp['state'] != flask.session.pop('state'):
        raise ValueError('The \'state\' parameter does not match.')

    if 'error' in authn_resp:
        return self._handle_error_response(authn_resp)

    # do token request
    args = {
        'code': authn_resp['code'],
        'redirect_uri': self.client.registration_response['redirect_uris'][0]
    }

    logger.debug('making token request')
    token_resp = self.client.do_access_token_request(
        state=authn_resp['state'],
        request_args=args,
        authn_method=self.client.registration_response.get('token_endpoint_auth_method', 'client_secret_basic')
    )
    logger.debug('received token response: %s', token_resp.to_json())

    if 'error' in token_resp:
        return self._handle_error_response(token_resp)

    flask.session['access_token'] = token_resp['access_token']

    id_token = None
    if 'id_token' in token_resp:
        id_token = token_resp['id_token']
        logger.debug('received id token: %s', id_token.to_json())

        if 'nonce' in id_token:
            if id_token['nonce'] != flask.session.pop('nonce'):
                raise ValueError('The \'nonce\' parameter does not match.')

        flask.session['id_token'] = id_token.to_dict()
        flask.session['id_token_jwt'] = id_token.to_jwt()
        # set the session as requested by the OP if we have no default
        if current_app.config.get('SESSION_PERMANENT'):
            flask.session.permanent = True
            flask.session.permanent_session_lifetime = id_token.get('exp') - time.time()

    # do userinfo request
    userinfo = self._do_userinfo_request(authn_resp['state'], self.userinfo_endpoint_method)

    if id_token and userinfo and userinfo['sub'] != id_token['sub']:
        raise ValueError('The \'sub\' of userinfo does not match \'sub\' of ID Token.')

    # store the current user session
    if userinfo:
        flask.session['userinfo'] = userinfo.to_dict()

    flask.session['last_authenticated'] = time.time()
    destination = flask.session.pop('destination')

    return redirect(destination)

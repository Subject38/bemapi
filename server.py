import argparse
import copy
import json
import traceback
from typing import Callable, Dict, Any, List
from flask import Flask, abort, request, Response, g  # type: ignore
from functools import wraps

app = Flask(
    __name__
)

SUPPORTED_VERSIONS = ['v1']


class APIException(Exception):
    pass


class BaseObject:

    def __init__(self, game: str, version: str, omnimix: bool) -> None:
        self.game = game
        self.version = version
        self.omnimix = omnimix

    def fetch_v1(self, idtype: str, ids: List[str], params: Dict[str, Any]) -> Any:
        raise APIException('Object fetch not supported for this version!')


class RecordsObject(BaseObject):

    def fetch_v1(self, idtype: str, ids: List[str], params: Dict[str, Any]) -> Any:
        return []


class StatisticsObject(BaseObject):

    def fetch_v1(self, idtype: str, ids: List[str], params: Dict[str, Any]) -> Any:
        return []


class ProfileObject(BaseObject):

    def fetch_v1(self, idtype: str, ids: List[str], params: Dict[str, Any]) -> Any:
        return []


def jsonify_response(data: Dict[str, Any], code: int=200) -> Response:
    return Response(
        json.dumps(data).encode('utf8'),
        content_type="application/json; charset=utf-8",
        status=code,
    )


@app.before_request
def before_request() -> None:
    g.authorized = False

    authkey = request.headers.get('Authorization')
    if authkey is not None:
        try:
            authtype, authtoken = authkey.split(' ', 1)
        except ValueError:
            authtype = None
            authtoken = None

        if authtype.lower() == 'token':
            g.authorized = authtoken == "dummy_token"


def authrequired(func: Callable) -> Callable:
    @wraps(func)
    def decoratedfunction(*args: Any, **kwargs: Any) -> Response:
        if not g.authorized:
            return jsonify_response(
                {'error': 'Unauthorized client!'},
                401,
            )
        else:
            return func(*args, **kwargs)
    return decoratedfunction


def jsonify(func: Callable) -> Callable:
    @wraps(func)
    def decoratedfunction(*args: Any, **kwargs: Any) -> Response:
        return jsonify_response(func(*args, **kwargs))
    return decoratedfunction


@app.errorhandler(Exception)
def server_exception(exception: Any) -> Response:
    stack = ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
    print(stack)

    return jsonify_response(
        {'error': 'Exception occured while processing request.'},
        500,
    )


@app.errorhandler(APIException)
def api_exception(exception: Any) -> Response:
    return jsonify_response(
        {'error': exception.message},
        exception.code,
    )


@app.errorhandler(500)
def server_error(error: Any) -> Response:
    return jsonify_response(
        {'error': 'Exception occured while processing request.'},
        500,
    )


@app.errorhandler(501)
def protocol_error(error: Any) -> Response:
    return jsonify_response(
        {'error': 'Unsupported protocol version in request.'},
        501,
    )


@app.errorhandler(400)
def bad_json(error: Any) -> Response:
    return jsonify_response(
        {'error': 'Request JSON could not be decoded.'},
        500,
    )


@app.errorhandler(404)
def unrecognized_object(error: Any) -> Response:
    return jsonify_response(
        {'error': 'Unrecognized request game/version or object.'},
        404,
    )


@app.errorhandler(405)
def invalid_request(error: Any) -> Response:
    return jsonify_response(
        {'error': 'Invalid request URI or method.'},
        405,
    )


@app.route('/<path:path>', methods=['GET', 'POST'])
@authrequired
def catch_all(path: str) -> Response:
    abort(405)


@app.route('/', methods=['GET', 'POST'])
@authrequired
@jsonify
def info() -> Dict[str, Any]:
    requestdata = request.get_json()
    if requestdata is None:
        raise APIException('Request JSON could not be decoded.')
    if requestdata:
        raise APIException('Unrecognized parameters for request.')

    return {
        'versions': SUPPORTED_VERSIONS,
        'name': 'Sample e-AMUSEMENT Server',
        'email': 'nobody@nowhere.com',
    }


@app.route('/<protoversion>/<requestgame>/<requestversion>', methods=['GET', 'POST'])
@authrequired
@jsonify
def lookup(protoversion: str, requestgame: str, requestversion: str) -> Dict[str, Any]:
    requestdata = request.get_json()
    for expected in ['type', 'ids', 'objects']:
        if expected not in requestdata:
            raise APIException('Missing parameters for request.')
    for param in requestdata:
        if param not in ['type', 'ids', 'objects', 'since', 'until']:
            raise APIException('Unrecognized parameters for request.')

    args = copy.deepcopy(requestdata)
    del args['type']
    del args['ids']
    del args['objects']

    if protoversion not in SUPPORTED_VERSIONS:
        # Don't know about this protocol version
        abort(501)

    if requestversion[0] == 'o':
        omnimix = True
        requestversion = requestversion[1:]
    else:
        omnimix = False

    idtype = requestdata['type']
    ids = requestdata['ids']
    if idtype not in ['card', 'song', 'instance', 'server']:
        raise APIException('Invalid ID type provided!')
    if idtype == 'card' and len(ids) == 0:
        raise APIException('Invalid number of IDs given!')
    if idtype == 'song' and len(ids) not in [1, 2]:
        raise APIException('Invalid number of IDs given!')
    if idtype == 'instance' and len(ids) != 3:
        raise APIException('Invalid number of IDs given!')
    if idtype == 'server' and len(ids) != 0:
        raise APIException('Invalid number of IDs given!')

    responsedata = {}
    for obj in requestdata['objects']:
        handler = {
            'records': RecordsObject,
            'profile': ProfileObject,
            'statistics': StatisticsObject,
        }.get(obj)
        if handler is None:
            # Don't support this object type
            abort(404)

        inst = handler(requestgame, requestversion, omnimix)
        try:
            fetchmethod = getattr(inst, 'fetch_{}'.format(protoversion))
        except AttributeError:
            # Don't know how to handle this object for this version
            abort(501)

        responsedata[obj] = fetchmethod(idtype, ids, args)

    return responsedata


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="An API services provider for eAmusement games")
    parser.add_argument("-p", "--port", help="Port to listen on. Defaults to 80", type=int, default=80)
    args = parser.parse_args()

    # Run the app
    app.run(host='0.0.0.0', port=args.port, debug=True)

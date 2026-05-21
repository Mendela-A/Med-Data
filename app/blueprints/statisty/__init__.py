from flask import Blueprint

statisty_bp = Blueprint('statisty', __name__, url_prefix='/statisty')

from . import routes

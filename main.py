import sys; sys.path[0:0] = ['lib']
from google.appengine.ext.webapp.util import run_wsgi_app
from gknot import app as application

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()
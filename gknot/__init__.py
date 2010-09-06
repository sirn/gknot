"""
    Gknot "Reef Knot" Build
    ----------------------------------------------------------------
    A Simple Web Page Encoding Conversation Service.
    Written by Kridsada Thanabulpong <sirn@ogsite.net>
    Licensed under BSD license.
    
    Special Thanks:
    - Gareth Rees (http://gareth-rees.livejournal.com/27148.html)
"""
import re
import os
from urllib import urlencode
from urllib2 import urlparse
from google.appengine.api import urlfetch
from google.appengine.api.memcache import Client

import httplib
import httplib2
import chardet

import html5lib
from html5lib import treebuilders
from html5lib import treewalkers
from html5lib import serializer

from flask import Flask, request, make_response
from flask import redirect, url_for, render_template

app = Flask(__name__)
memcache = Client()
http = httplib2.Http(memcache)


# Static page

@app.route('/')
def index():
    """Return an introduction page to the service."""
    return render_template('index.html', **locals())


# Redirection page

@app.route('/soup')
def land():
    """Landing page for bookmarklet. Redirect user to the proper URL."""
    if 'source' not in request.args:
        return redirect('/')
    source = urlparse.urlparse(request.args['source'])
    
    # Sanitize path and get rid of extra leading slash, leaving them there
    # probably won't cause any problem, just do it for cleaning's sake.
    path = re.sub('\/(\/+)', '/', source.path)
    path = re.sub('^\/', '', path)
    
    endpoint = url_for('soup',
        protocol=source.scheme,
        domain=source.netloc,
        path=path if path != '/' else None,
    )
    if source.query:
        endpoint += '?%s' % source.query
    
    return redirect(endpoint)


# Conversation Handler

url_attributes = [
    ('a', 'href'),
    ('applet', 'codebase'),
    ('area', 'href'),
    ('blockquote', 'cite'),
    ('body', 'background'),
    ('td', 'background'),
    ('del', 'cite'),
    ('form', 'action'),
    ('frame', 'longdesc'),
    ('frame', 'src'),
    ('iframe', 'longdesc'),
    ('iframe', 'src'),
    ('head', 'profile'),
    ('img', 'longdesc'),
    ('img', 'src'),
    ('img', 'usemap'),
    ('input', 'src'),
    ('input', 'usemap'),
    ('ins', 'cite'),
    ('link', 'href'),
    ('object', 'classid'),
    ('object', 'codebase'),
    ('object', 'data'),
    ('object', 'usemap'),
    ('q', 'cite'),
    ('script', 'src'),
    ('param', 'value'),
    ('embed', 'src'),
]

class ConversationError(Exception): pass

def get_domain_parts(netloc):
    parts = netloc.lower().split(':', 1)
    return parts[0], parts[1] if len(parts) >= 2 else '80'

def convert(protocol, domain, path, query):
    """Convert any webpage into UTF-8 and rewrite all internal links
    as absolute links.  If the encoding detection confidence is less
    than 0.5, an error is thrown.
    """
    
    local = get_domain_parts(urlparse.urlparse(request.host_url).netloc)
    remote = get_domain_parts(domain)
    if local == remote:
        raise ConversationError('space-time continuum interruption')
    
    if protocol.lower() not in ('http', 'https'):
        raise ConversationError('only HTTP and HTTPS are supported')
    
    # If we use query string, then the user will have to handle query string
    # escaping by themselves. The current "fragmented" URL is done so that
    # prefixing the target URL and replacing `://` with `/` is all it
    # requires to use the service.
    urltuple = (protocol, domain, path, None, urlencode(query), None)
    pageurl = urlparse.urlunparse(urltuple)
    
    # httplib2 is used so that HTTP requests are properly cached according
    # to the source's header. Any page with embedded CSS or JavaScript that
    # request external resource from relative path will make a hit to this
    # application, thus we redirect out all non-HTML page to the original
    # location.
    # 
    # TODO:
    # - Attempt to convert text/plain.
    try:
        headers, body = http.request(pageurl)
        if headers.status not in (200, 302, 304):
            msg = (headers.status, httplib.responses[headers.status])
            raise ConversationError('could not fetch web page, %s %s' % msg)
        baseurl = headers['content-location']
        if 'html' not in headers['content-type']:
            return redirect(baseurl)
    except urlfetch.DownloadError, e:
        raise ConversationError('could not fetch web page, invalid URL')
    
    # While html5lib could detect the encoding by itself, it is a lot less
    # accurate than chardet, e.g. http://www.nectec.or.th/tindex.html.
    # If the webpage has less than 0.5 confidence, then it's probably
    # too broken to read anyway. Just reject it and save some CPU time.
    detection = chardet.detect(body)
    if detection['confidence'] <= 0.5:
        raise ConversationError('could not detect page encoding')
    content = body.decode(detection['encoding'])
    
    # Base URL is taken from Content-Location return by httplib2 to
    # make sure redirection is properly followed.
    #
    # TODO:
    # - Attempt to rewrite resources located in embedded CSS/JavaScript.
    parser = html5lib.HTMLParser(tree=treebuilders.getTreeBuilder('dom'))
    document = parser.parse(content)
    for tag, attr in url_attributes:
        for element in document.getElementsByTagName(tag):
            href = element.getAttribute(attr)
            if href:
                element.setAttribute(attr, urlparse.urljoin(baseurl, href))
    
    # Most browser will probably detect UTF-8 and render it as so anyway,
    # but let's took the safe bet and rewrite it anyway.
    head = document.getElementsByTagName('head')[0]
    for meta in document.getElementsByTagName('meta'):
        if meta.getAttribute('http-equiv').lower() == 'content-type':
            head.removeChild(meta)
            break
    charset = document.createElement('meta')
    charset.setAttribute('charset', 'utf-8')
    head.appendChild(charset)
    
    # Return! Finally!
    tree_walker = treewalkers.getTreeWalker('dom')
    html_serializer = serializer.htmlserializer.HTMLSerializer()
    result = ''.join(html_serializer.serialize(tree_walker(document)))
    return result.encode('utf-8')

@app.route('/soup/<string:protocol>/<string:domain>/')
@app.route('/soup/<string:protocol>/<string:domain>/<path:path>')
def soup(protocol='http', domain='example.com', path='/'):
    """Pass the processing to `convert` and handle errors."""
    try:
        return convert(protocol, domain, path, request.args)
    except ConversationError, e:
        response = make_response('Error: %s.' % e)
        response.headers['Content-Type'] = 'text/plain'
        return response


if __name__ == '__main__':
    app.run()
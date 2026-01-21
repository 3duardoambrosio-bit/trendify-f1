import os, urllib.request, urllib.parse
from urllib.error import HTTPError

t=os.environ.get("META_ACCESS_TOKEN","")
u="https://graph.facebook.com/v22.0/me?" + urllib.parse.urlencode({"fields":"id,name","access_token":t})
try:
    print(urllib.request.urlopen(u, timeout=30).read().decode("utf-8","replace"))
except HTTPError as e:
    print(e.read().decode("utf-8","replace"))

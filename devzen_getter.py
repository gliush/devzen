#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pprint
import string
import sys
import datetime
import os
import re
from collections import defaultdict
from urllib2 import urlopen
from htmlentitydefs import name2codepoint
import urllib

from HTMLParser import HTMLParser

def help():
    print "get devzen episode and convert it to correct markdown into correct path (src/_posts/...-episode....md)"
    print "Usage:"
    print "%s <NUM>" % sys.argv[0]
    print "    where <NUM> - is the episode number"
    sys.exit(2)


class DevzenParser(HTMLParser):
    def __init__(self):
        self.tags = []
        self.attrs = None
        self.section = None
        self.chars = u''
        self.podcast = defaultdict(str)
        HTMLParser.__init__(self)

    def handle_starttag(self, tag, attrs):
        #print "enter %s" % tag
        self.tags.append(tag)
        self.attrs = attrs
    def handle_endtag(self, tag):
        #print "exit %s" % tag
        self.tags.pop()
        self.attrs = None
    def handle_entityref(self, name):
        c = unichr(name2codepoint[name])
        self.chars += c
        #print "Named ent:", c
    def handle_charref(self, name):
        if name.startswith('x'):
            c = unichr(int(name[1:], 16))
        else:
            c = unichr(int(name))
        self.chars += c
        #print "Num ent  :", c
    def handle_data(self, data):
        tags = "/".join(self.tags)
        #print tags,": ", data
        data = self.chars + data
        self.chars = u''
        if tags == "html/head/title":
            if not 'DevZen Podcast' in data: # убираем лишний везде "DevZen Podcast"
                self.podcast["title"] += data
        elif tags == "html/body/div/div/header/section/div/article/header/div/time":
            self.podcast["publish_date"] = datetime.datetime.strptime(data, "%d.%m.%Y")
            self.podcast["record_date"] = datetime.datetime.strptime(data, "%d.%m.%Y")
            self.podcast["publish_date_str"] = datetime.datetime.strptime(data, "%d.%m.%Y").isoformat()
            self.podcast["record_date_str"] = datetime.datetime.strptime(data, "%d.%m.%Y").isoformat()
        elif tags.startswith("html/body/div/div/header/section/div/article/div/p"):
            if u'Голоса выпуска' in data:
                self.section = "hosts"
            elif u'Подкаст' in data:
                self.section = "episode_url"
            elif u'Темы выпуска' in data:
                self.podcast["summary"] = re.sub(u"Темы выпуска: ", u"", data)
                self.section = None

            if tags == "html/body/div/div/header/section/div/article/div/p/a":
                if self.section == "hosts":
                    if not "hosts" in self.podcast:
                        self.podcast["hosts"] = []
                    link = dict(self.attrs)
                    link["text"] = data
                    self.podcast["hosts"].append(link)
                elif self.section == "episode_url":
                    link = dict(self.attrs)
                    self.podcast["episode_url"] = link["href"]
                    self.podcast["episode_file"] = link["download"]
                    site = urllib.urlopen(link["href"])
                    meta = site.info()
                    self.podcast["length"] = meta.getheaders("Content-Length")[0]

        elif tags == "html/body/div/div/header/section/div/article/div/ul/li/a":
            if self.attrs:
                data = string.replace(data, "|", "\|")
                #print "AA%sAA" % data
                link = dict(self.attrs)
                if not "shownotes" in self.podcast:
                    link["text"] = data
                    self.podcast["shownotes"] = []
                elif self.podcast["shownotes"][-1]["href"] == link["href"]:
                    # more text to the previous link
                    link = self.podcast["shownotes"].pop()
                    link["text"] += " " + data
                else:
                    # new link
                    link["text"] = data
                self.podcast["shownotes"].append(link)
        else:
            self.section = None

if len(sys.argv) != 2:
    help()

try:
    episode = int(sys.argv[1])
except:
    help()


permalink = "/episode-%04d/" % episode
URL = "http://devzen.ru" + permalink


parser = DevzenParser()
parser.podcast["permalink"] = permalink

#content = open("/tmp/aa.html", 'r').read().decode('utf-8')
#print content
content = urlopen(URL).read().decode('utf-8')
#open("/tmp/content.html", 'w').write(content.encode('utf-8'))
parser.feed(content)
#pprint.pprint(parser.podcast)

site_dir = os.path.dirname(sys.argv[0])

filename = parser.podcast["publish_date"].strftime("%Y-%m-%d") + "-episode-%04d" % episode
output = reduce(os.path.join ,[site_dir, "src", "_posts", filename]) + ".md"

fd = open(output, 'w')
#fd = sys.stdout
fd.write(("""---
layout: post
title: %(title)s
permalink: %(permalink)s
episode_url: %(episode_url)s
record_date: %(record_date_str)s
publish_date: %(publish_date_str)s
length: %(length)s
background_music:
 - Plastic3 - Corporate Rock Motivation Loop 4: http://www.jamendo.com/en/track/1109994/corporate-rock-motivation-loop-4
summary: "%(summary)s"
authors:
""" % parser.podcast).encode('utf-8'))

for h in parser.podcast["hosts"]:
    fd.write((" - %(text)s: %(href)s\n" % h).encode('utf-8'))

fd.write(u'---\n\n#### Шоу нотес:\n\n'.encode('utf-8')) 

for s in parser.podcast["shownotes"]:
    fd.write( ("* [%(text)s](%(href)s)\n" % s).encode('utf-8'))

print "OK\ncheck " + output

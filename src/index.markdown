---
layout: default
title: DevZen Podcast. Подкаст о программировании, IT и смежных темах
---

### Последние выпуски

<ul class="posts">
  {% for post in site.posts %}
    <li><span>{{ post.date | date: "%d/%m/%Y" }}</span> &raquo; <a href="{{ post.url }}">{{ post.title }}</a> <a href="{{ post.url }}#disqus_thread"></a></a></li>
  {% endfor %}
</ul>

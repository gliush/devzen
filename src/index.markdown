---
layout: default
title: DevZen Podcast. Подкаст о программировании, IT и смежных темах
---

### Последние выпуски

<ul class="posts">
  {% for post in site.posts %}
    <li><span>{{ post.date | date: "%d/%m/%Y" }}</span> &raquo; 
        <a href="{{ post.url }}">{{ post.title }}</a> 
        (<a data-disqus-identifier="http://devzen.ru{{ post.permalink }}" href="{{ post.url }}#disqus_thread">Комментарии</a>)
    </li>
  {% endfor %}
</ul>

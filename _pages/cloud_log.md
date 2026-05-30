---
layout: page
permalink: /log/
title: cloudspotting
description: Interesting clouds in reverse chronological order.
nav: true
nav_order: 6
---

{% assign cloud_entries = site.data.clouds %}

{% for entry in cloud_entries %}
<hr>

{% for row in entry.rows %}
<div class="row mt-3">
  {% for media in row %}
    <div class="col-sm mt-3 mt-md-0">
      {% if media.type == "video" %}
        {% include video.liquid path=media.path class="img-fluid rounded z-depth-1" controls=true %}
      {% else %}
        {% include figure.liquid loading="eager" path=media.path class="img-fluid rounded z-depth-1" zoomable=true %}
      {% endif %}
    </div>
  {% endfor %}
</div>
{% endfor %}
<div class="caption">
  {{ entry.caption }}
</div>

{% endfor %}
<hr>

import csv
from datetime import datetime

def get_ordinal_suffix(day: int) -> str:
    return {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th') if day not in (11, 12, 13) else 'th'

css_template = '<div class="row mt-3">\n\t<div class="col-sm mt-3 mt-md-0">\n\t\t{{% include figure.liquid loading="eager" path="assets/img/clouds/{0}.jpeg" class="img-fluid rounded z-depth-1" zoomable=true %}}\n\t</div>\n</div>\n<div class="caption">\n\t{1}. {2}. {3}.\n</div>\n\n<hr>'

with open('clouds.csv', newline='\n') as f:
    reader = csv.reader(f, delimiter=',')
    for row in reader:
        filename = row[0]
        date = datetime.strptime(filename[:10], "%Y-%m-%d")
        day = datetime.strftime(date, "%d")
        datestring = '{dt.day}{0} {dt:%B} {dt.year}'.format(get_ordinal_suffix(int(day)), dt=date)
        cloud = row[1]
        location = row[2]

        print(css_template.format(filename, cloud, location, datestring))



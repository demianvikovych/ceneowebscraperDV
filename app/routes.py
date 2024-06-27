from app import app
from app import utils
from flask import render_template, request, redirect, url_for, send_file
import requests
import os
import json
import pandas as pd
import numpy as np
from io import BytesIO
from bs4 import BeautifulSoup
from matplotlib import pyplot as plt
import matplotlib
import xlsxwriter
matplotlib.use('Agg')

@app.route('/')
@app.route('/index')
def index():
  return render_template("index.html")

@app.route('/extract', methods=['GET', 'POST'])
def extract():
  if request.method == 'POST':
    product_id = request.form.get('product_id')
    url = f"https://www.ceneo.pl/{product_id}#tab=reviews"
    response = requests.get(url)

    if response.status_code == requests.codes['ok']:
      page_dom = BeautifulSoup(response.text, "html.parser")

      try:
        opinions_count = page_dom.select_one("a.product-review__link > span").get_text().strip()
      except AttributeError:
        opinions_count = 0

      if opinions_count:
        product_name = page_dom.select_one("h1").get_text().strip()
        url = f"https://www.ceneo.pl/{product_id}#tab=reviews"
        all_opinions = []
        while(url):
          print(url)
          response = requests.get(url)
          page_dom = BeautifulSoup(response.text, "html.parser")
          opinions = page_dom.select("div.js_product-review")
          for opinion in opinions:
            single_opinion = {
              key: utils.extract(opinion, *value)
                for key, value in utils.selectors.items()
            }
            for key, value in utils.transformations.items():
              single_opinion[key] = value(single_opinion[key])
            all_opinions.append(single_opinion)
          try:
            url = "https://www.ceneo.pl"+utils.extract(page_dom, "a.pagination__next", "href")
          except TypeError:
            url = None
        if not os.path.exists("app/opinions"):
          os.mkdir("app/opinions")
        jf = open(f"app/opinions/{product_id}.json", "w", encoding="UTF-8")
        json.dump(all_opinions, jf, indent=4, ensure_ascii=False)
        jf.close()
        opinions = pd.DataFrame.from_dict(all_opinions)
        MAX_SCORE = 5
        opinions.score = opinions.score.apply(lambda s: round(s*MAX_SCORE, 1))
        opinions_count = opinions.index.size
        pros_count = opinions.pros.apply(lambda p: None if not p else p).count()
        cons_count = opinions.cons.apply(lambda c: None if not c else c).count()
        average_score = opinions.score.mean()
        score_distribution = opinions.score.value_counts().reindex(np.arange(0,5.5,0.5), fill_value = 0)
        recommendation_distribution = opinions.recommendation.value_counts(dropna=False).reindex([True, False, np.nan], fill_value = 0)
        product = {
          'product_id': product_id,
          'product_name': product_name,
          'opinions_count': int(opinions_count),
          'pros_count': int(pros_count),
          'cons_count': int(cons_count),
          'average_score': average_score,
          'score_distribution': score_distribution.to_dict(),
          'recommendation_distribution': recommendation_distribution.to_dict()
        }
        if not os.path.exists("app/products"):
          os.mkdir("app/products")
        jf = open(f"app/products/{product_id}.json", "w", encoding="UTF-8")
        json.dump(product, jf, indent=4, ensure_ascii=False)
        jf.close()
        if not os.path.exists("app/static/charts"):
            os.makedirs("app/static/charts")

        
        fig, ax = plt.subplots()
        score_distribution.plot.bar(color="orange")
        plt.xlabel("Number of stars")
        plt.ylabel("Number of opinions")
        plt.title(f"Score histogram for {product_name}")
        plt.xticks(rotation=0)
        ax.bar_label(ax.containers[0], label_type='edge', fmt=lambda l: int(l) if l else "")
        plt.savefig(f"app/static/charts/{product_id}_score.png")
        plt.close()

        
        fig, ax = plt.subplots()
        recommendation_distribution.plot.pie(
          labels=["Recommend", "Not recommend", "Indifferent"],
          label="",
          colors=["green", "red", "whitesmoke"],
          autopct=lambda l: "{:1.1f}%".format(l) if l else ""
        )
        plt.title(f"Recommendations shares for {product_name}")
        plt.savefig(f"app/static/charts/{product_id}_recommendation.png")
        plt.close()

        return redirect(url_for('product', product_id = product_id))
      return render_template('extract.html', error = "Product has no opinions")
    return render_template('extract.html', error = "Product does not exist")
  return render_template("extract.html")

@app.route('/products')
def products():
  if os.path.exists("app/opinions"):
    products = [filename.split(".")[0] for filename in os.listdir("app/opinions")]
  else: products = []
  products_list = []
  for product in products:
    jf = open(f"app/products/{product}.json", "r", encoding="UTF-8")
    single_product = json.load(jf)
    products_list.append(single_product)
  return render_template("products.html", products = products_list)


@app.route('/author')
def author():
  return render_template("author.html")

@app.route('/product/<product_id>')
def product(product_id):
  opinions = pd.read_json(f"app/opinions/{product_id}.json")

  def format_content(content):
    if isinstance(content, dict):
      return f"Polish: <br>{content.get('pl')} <br><br> English: <br>{content.get('en')}"
    return "No content available"

  def format_pros(pros):
    if isinstance(pros, dict):
      pl_list = pros.get('pl')
      en_list = pros.get('en')
      return f"Polish: <br>{'<br>'.join(pl_list)} <br><br> English: <br>{'<br>'.join(en_list)}"
    return "No pros available"

  def format_cons(cons):
    if isinstance(cons, dict):
      pl_list = cons.get('pl')
      en_list = cons.get('en')
      return f"Polish: <br>{'<br>'.join(pl_list)} <br><br> English: <br>{'<br>'.join(en_list)}"
    return "No cons available"

  opinions['content'] = opinions['content'].apply(format_content)
  opinions['pros'] = opinions['pros'].apply(format_pros)
  opinions['cons'] = opinions['cons'].apply(format_cons)

  return render_template("product.html", product_id=product_id, opinions=opinions.to_html(table_id="opinions", escape=False))

@app.route('/charts/<product_id>')
def charts(product_id):
  return render_template("charts.html", product_id=product_id)

@app.route('/download/json/<product_id>')
def download_json(product_id):
  return send_file(f"products/{product_id}.json", mimetype='text/json', download_name=f'{product_id}.json', as_attachment=True)

@app.route('/download/csv/<product_id>')
def download_csv(product_id):
  opinions = pd.read_json(f"app/opinions/{product_id}.json")
  opinions = pd.concat([opinions.drop(['content'], axis=1), opinions['content'].apply(pd.Series)], axis=1)
  response_stream = BytesIO(opinions.to_csv().encode())
  return send_file(response_stream, mimetype='text/csv', download_name=f'{product_id}.csv', as_attachment=True)

@app.route('/download/xlsx/<product_id>')
def download_xlsx(product_id):
  opinions = pd.read_json(f"app/opinions/{product_id}.json")
  buffer = BytesIO()
  with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
    opinions.to_excel(writer)
  buffer.seek(0)
  return send_file(buffer, mimetype='text/xlsx', download_name=f'{product_id}.xlsx', as_attachment=True)

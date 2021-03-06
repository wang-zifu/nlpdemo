from flask import Flask, jsonify, request
from flask_cors import CORS, cross_origin

import torch

import spacy
from spacy.tokens import Span
from spacy.matcher import PhraseMatcher
        
from transformers import AutoTokenizer, AutoModelForQuestionAnswering, pipeline 

from api import app

import api.src as src
from api.src import get_dataset
from api.src import nlp as NLP

BERT_MODEL = "bert-large-uncased-whole-word-masking-finetuned-squad"
word_analogy_file = "glove.6B.50d.txt"

nlp = None
classifier = None
summarizer_ = None
tokenizer = None
question_model = None
word_analogy_model = None

cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'


""" 
Description:
    Global endpoint to perform Text Mining and Sentiment Analysis on a corpus
"""
@app.route("/analysis", methods=["POST"])
@cross_origin()
def analyze():
    try:
        global classifier
        if request.method == 'POST':
            import string

            data = request.get_json()
            assert data["text"]
            doc = make_doc(data["text"].replace("@", ""))

            res = {}
            if "persons" in data["configs"]:
                res["PERSONS"] = NLP.get_persons(doc)
            if "entities" in data["configs"]:
                res["ENTITIES"] = NLP.get_entities(doc)  
            if "countries" in data["configs"]:
                res["COUNTRIES"] = NLP.get_countries(doc)
            if "verbs" in data["configs"]:
                res["VERBS"] = NLP.get_verbs(doc)
            if "sentiment" in data["configs"]:
                if classifier is None:
                    classifier = pipeline("sentiment-analysis", device=0 if torch.cuda.is_available() else -1)
                data = request.get_json()
                text = data["text"].translate(str.maketrans('', '', string.punctuation))
                sa = NLP.sentiment_analysis(text, classifier)
                res["SENTIMENT_ANALYSIS"] = sa
                
            timer = NLP.get_timer()
            res["time_spent"] = timer
        return jsonify(res)
    except:
        raise


@app.route("/dataset/<int:size>", methods=["GET"])
@cross_origin()
def dataset(size=10):
    if request.method == 'GET':
        dataset = get_dataset.load()
        return jsonify(dataset[0:size:])


""" 
Description:
    Load Dataset from Yelp review file
Args:
    start (ind)
    end (int)
"""
@app.route("/yelp-dataset/<int:start>/<int:end>", methods=["GET"])
@cross_origin()
def yelp_dataset(start=0, end=10):
    try:
        if request.method == 'GET':
            dataset, pages = get_dataset.load_yelp_reviews(start=start, end=end)
            return jsonify({
                "dataset": dataset,
                "pages": pages
            })
    except:
        raise


@app.route("/sentiment-analysis", methods=["POST"])
@cross_origin()
def sentiment_analysis():
    assert request.method == "POST"

    import string
    
    data = request.get_json()
    text = data["text"].translate(str.maketrans('', '', string.punctuation))
    res = NLP.sentiment_analysis(text)
    return jsonify(res)


""" 
Description:
    Make analysi prediction on a review
Returns:
    label (str)
    score (float)
"""
@app.route("/answer-question", methods=["POST"])
@cross_origin()
def answer_question():
    global question_model, tokenizer
    assert request.method == "POST"

    if question_model is None:
        question_model = AutoModelForQuestionAnswering.from_pretrained(BERT_MODEL, resume_download=True)
        tokenizer = AutoTokenizer.from_pretrained(BERT_MODEL, resume_download=True)

    data = request.get_json()
    answer = NLP.answer_question(
        question=data["question"],
        TEXT=data["text"],
        tokenizer=tokenizer,
        model=question_model
    )
    return jsonify({"answer": answer})        


@app.route("/summarizer", methods=["POST"])
@cross_origin()
def summarizer():
    global summarizer_
    
    assert request.method == "POST"

    if summarizer_ is None:
        summarizer_ = pipeline("summarization")
    
    data = request.get_json()
    summarized = summarizer_(
        data["text"],
        max_length=round(int(len(data["text"]) * 0.2) / 2),
        min_length=30,
        do_sample=False
    )
    summary_text = summarized[0]["summary_text"]
    return jsonify({ "summary_text": summary_text })  


@app.route("/word-analogy", methods=["POST"])
@cross_origin()
def word_analogy():
    global word_analogy_model
    assert request.method == "POST"

    if word_analogy_model is None:
        import os.path
        word_analogy_model = NLP.WorldAnalogyModel.from_embeddings_file(os.path.join("dataset", word_analogy_file))
    data = request.get_json()
    assert data["word1"]

    word2 = data["word2"] if "word2" in data else None
    word3 = data["word3"] if "word3" in data else None
    analogies = word_analogy_model.compute_analogy(data["word1"], word2=word2, word3=word3)

    return jsonify({ "analogies": analogies })

@app.route("/get-in-touch", methods=["POST"])
@cross_origin()
def send_email():
    try:
        assert request.method == "POST"
        data = request.get_json()
        assert "sender" in data
        assert "message" in data
        assert "fullname" in data

        from api import mail
        mail.send_mail_tls(
            user_email=data["sender"],
            fullname=data["fullname"],
            message_=data["message"]
        )
        return jsonify({ "success": True })
    except:
        jsonify({ "success": False })

def make_doc(TEXT):
    global nlp
    if nlp is None:
        nlp = spacy.load("en_core_web_sm")
    return nlp(TEXT)
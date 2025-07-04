from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import pandas as pd
import joblib
from sklearn.metrics.pairwise import cosine_similarity
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Load data and models
df = pd.read_csv("processed_movies.csv")
tfidf = joblib.load("tfidf_vectorizer.pkl")
tfidf_matrix = joblib.load("tfidf_matrix.pkl")

# 🔑 Your TMDB API key
TMDB_API_KEY = "cf79ad9b3dc6fe6f2cd294b1ea756d62"

@lru_cache(maxsize=10000)
def fetch_movie_features_cached(movie_id):
    return fetch_movie_features(movie_id)

@lru_cache(maxsize=10000)
def fetch_poster_url_cached(movie_id):
    return fetch_poster_url(movie_id)

@lru_cache(maxsize=10000)
def fetch_movie_details_cached(movie_id):
    return fetch_movie_details(movie_id)

def fetch_movie_features(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=en-US"
    res = requests.get(url)
    if res.status_code != 200:
        return ""
    data = res.json()
    genres = " ".join([g['name'].replace(" ", "") for g in data.get('genres', [])])
    tagline = data.get('tagline', '').replace(" ", "")
    
    # Extract year from release date
    release_date = data.get('release_date', '')
    year = 'unknown'
    decade = 'unknown'
    if release_date:
        try:
            year = release_date.split('-')[0]
            year_int = int(year)
            decade = f"{(year_int // 10) * 10}s"
        except:
            pass
    
    keywords = fetch_keywords(movie_id)
    return f"{genres} {keywords} {tagline} {year} {decade}".strip()

def fetch_keywords(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/keywords?api_key={TMDB_API_KEY}"
    res = requests.get(url)
    if res.status_code != 200:
        return ""
    data = res.json()
    return " ".join([k['name'].replace(" ", "") for k in data.get('keywords', [])])

def fetch_poster_url(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=en-US"
    res = requests.get(url)
    if res.status_code != 200:
        return ""
    data = res.json()
    poster_path = data.get('poster_path', '')
    return f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""

def fetch_movie_details(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=en-US"
    res = requests.get(url)
    if res.status_code != 200:
        return {}
    return res.json()

@app.route('/clear-cache', methods=['POST'])
def clear_cache():
    """Clear all caches to ensure fresh recommendations"""
    try:
        fetch_movie_features_cached.cache_clear()
        fetch_poster_url_cached.cache_clear()
        fetch_movie_details_cached.cache_clear()
        print("All caches cleared successfully")
        return jsonify({"message": "Cache cleared successfully"}), 200
    except Exception as e:
        print(f"Error clearing cache: {e}")
        return jsonify({"error": "Failed to clear cache"}), 500

@app.route('/recommend', methods=['POST'])
def recommend_history():
    data = request.get_json()
    ids = data.get("watchedIds", [])
    if not ids:
        return jsonify({"error": "No movie IDs provided"}), 400

    # Clear caches to ensure fresh data
    fetch_movie_features_cached.cache_clear()
    fetch_poster_url_cached.cache_clear()
    fetch_movie_details_cached.cache_clear()

    # Parallel fetch features for watched movies
    combined_text = ""
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_id = {executor.submit(fetch_movie_features_cached, movie_id): movie_id for movie_id in ids}
        for future in as_completed(future_to_id):
            combined_text += " " + future.result()

    if not combined_text.strip():
        return jsonify({"error": "Failed to fetch data for given IDs"}), 500

    input_vec = tfidf.transform([combined_text])
    similarity_scores = cosine_similarity(input_vec, tfidf_matrix).flatten()
    top_indices = similarity_scores.argsort()[::-1]

    watched_set = set(ids)
    recommendations = []
    poster_futures = []
    poster_results = {}
    details_results = {}

    # Prepare top movie IDs to fetch posters and details for (in parallel)
    top_movie_ids = []
    for i in top_indices:
        movie = df.iloc[i]
        movie_id = int(movie['id'])
        if movie_id in watched_set:
            continue
        top_movie_ids.append(movie_id)
        if len(top_movie_ids) == 20:
            break

    # Parallel fetch posters and details
    with ThreadPoolExecutor(max_workers=8) as executor:
        # Fetch posters
        poster_futures = {executor.submit(fetch_poster_url_cached, movie_id): movie_id for movie_id in top_movie_ids}
        # Fetch details
        details_futures = {executor.submit(fetch_movie_details_cached, movie_id): movie_id for movie_id in top_movie_ids}
        
        # Collect poster results
        for future in as_completed(poster_futures):
            poster_results[poster_futures[future]] = future.result()
        
        # Collect details results
        for future in as_completed(details_futures):
            details_results[details_futures[future]] = future.result()

    # Build recommendations (up to 12)
    for i in top_indices:
        movie = df.iloc[i]
        movie_id = int(movie['id'])
        if movie_id in watched_set:
            continue
        
        poster_url = poster_results.get(movie_id, "")
        details = details_results.get(movie_id, {})
        
        # Extract year from release date
        release_date = details.get('release_date', '')
        year = 'Unknown'
        if release_date:
            try:
                year = release_date.split('-')[0]
            except:
                pass
        
        recommendations.append({
            "id": movie_id,
            "title": movie['original_title'],
            "poster": poster_url,
            "year": year,
            "rating": details.get('vote_average', 0),
            "overview": details.get('overview', '')[:150] + '...' if details.get('overview') else ''
        })
        if len(recommendations) == 12:
            break
    
    return jsonify(recommendations)

if __name__ == '__main__':
    app.run(debug=True)

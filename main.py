import os
import sqlite3
import time
import json
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from jinja2 import DictLoader

# ==========================================
# CONFIGURATION
# ==========================================
app = Flask(__name__)
app.secret_key = 'premium_store_secret_key_v3_ultimate'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

DB_NAME = "atoz_mobile.db"

PROVINCES = [
    "Koshi", "Madhesh", "Bagmati", 
    "Gandaki", "Lumbini", "Karnali", 
    "Sudurpashchim"
]

# Premium Themes
THEMES = {
    "Modern White": {
        "nav_bg": "bg-white/95 backdrop-blur-md border-b border-gray-200",
        "nav_text": "text-gray-800",
        "body_bg": "bg-gray-50",
        "card_bg": "bg-white",
        "btn_primary": "bg-gray-900 hover:bg-gray-800 text-white",
        "accent_text": "text-gray-900",
    },
    "Dashain Festival": {
        "nav_bg": "bg-red-700 text-white shadow-lg",
        "nav_text": "text-white",
        "body_bg": "bg-red-50",
        "card_bg": "bg-white border-red-100",
        "btn_primary": "bg-red-600 hover:bg-red-700 text-white",
        "accent_text": "text-red-700",
    },
    "Tihar Night": {
        "nav_bg": "bg-slate-900 text-white border-b border-purple-500",
        "nav_text": "text-gray-100",
        "body_bg": "bg-slate-900",
        "card_bg": "bg-slate-800 border border-slate-700 text-white",
        "btn_primary": "bg-purple-600 hover:bg-purple-700 text-white",
        "accent_text": "text-purple-400",
    }
}

# ==========================================
# DATABASE HANDLING
# ==========================================
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_NAME)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        # Create Tables
        db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            mobile TEXT,
            province TEXT,
            is_admin INTEGER DEFAULT 0
        )''')
        
        db.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            discount_price REAL,
            description TEXT,
            image_url TEXT
        )''')

        db.execute('''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            full_name TEXT,
            address TEXT,
            mobile TEXT,
            total_amount REAL,
            status TEXT DEFAULT 'Pending',
            items_summary TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        db.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')

        db.execute('''CREATE TABLE IF NOT EXISTS payment_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            method_name TEXT,
            account_number TEXT,
            qr_image TEXT
        )''')
        
        # Create Default Admin
        cur = db.execute("SELECT * FROM users WHERE username = ?", ('admin@gmail.com',))
        if not cur.fetchone():
            hashed = generate_password_hash('admin123')
            db.execute("INSERT INTO users (username, password, is_admin, full_name) VALUES (?, ?, 1, 'Super Admin')", 
                       ('admin@gmail.com', hashed))
        
        # Default Settings
        cur = db.execute("SELECT * FROM settings WHERE key = 'theme'")
        if not cur.fetchone():
            db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ('theme', 'Modern White'))
            db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ('site_title', 'AtoZ Store'))

        db.commit()

# ==========================================
# HTML TEMPLATES
# ==========================================

LAYOUT_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{{ site_title }}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Poppins', sans-serif; }
        /* Remove Serif fonts globally */
        h1, h2, h3, h4, h5, h6, p, span, div, a { font-family: 'Poppins', sans-serif !important; }
        
        .loader-wrapper {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: #ffffff; z-index: 9999; display: flex;
            justify-content: center; align-items: center;
            transition: opacity 0.5s ease;
        }
        .spinner {
            width: 50px; height: 50px; border: 5px solid #f3f3f3;
            border-top: 5px solid #333; border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        
        /* Modal Styles */
        .modal { transition: opacity 0.25s ease; }
        body.modal-active { overflow-x: hidden; overflow-y: hidden !important; }
    </style>
</head>
<body class="{{ theme.body_bg }} min-h-screen flex flex-col text-gray-800">

    <!-- Loading Screen -->
    <div id="loader" class="loader-wrapper">
        <div class="spinner"></div>
    </div>

    <!-- Navigation -->
    <header class="{{ theme.nav_bg }} fixed w-full top-0 z-40 transition-all duration-300 shadow-sm">
        <div class="w-full max-w-[1600px] mx-auto px-4 md:px-8 h-16 flex justify-between items-center">
            <a href="/" class="text-2xl font-bold tracking-tight {{ theme.nav_text }}">
                <i class="fas fa-bolt mr-1 text-yellow-500"></i> {{ site_title }}
            </a>
            
            <nav class="hidden md:flex items-center gap-8 font-medium text-sm uppercase tracking-wide {{ theme.nav_text }}">
                <a href="/" class="hover:text-red-500 transition">Home</a>
                <a href="/cart" class="hover:text-red-500 transition relative">
                    Cart
                    {% if session.get('cart') %}
                    <span class="absolute -top-2 -right-3 bg-red-600 text-white text-[10px] w-5 h-5 flex items-center justify-center rounded-full">{{ session.get('cart')|length }}</span>
                    {% endif %}
                </a>
                {% if current_user %}
                    <a href="/profile" class="hover:text-red-500 transition">My Profile</a>
                    {% if current_user.is_admin %}
                        <a href="/admin" class="bg-red-600 text-white px-4 py-2 rounded-full text-xs hover:bg-red-700 shadow-lg">Admin Panel</a>
                    {% endif %}
                {% else %}
                    <a href="/login" class="bg-gray-900 text-white px-6 py-2 rounded-full hover:bg-gray-800 transition shadow-lg">Login</a>
                {% endif %}
            </nav>

            <!-- Mobile Cart Icon -->
            <a href="/cart" class="md:hidden {{ theme.nav_text }} relative p-2">
                <i class="fas fa-shopping-bag text-xl"></i>
                {% if session.get('cart') %}
                    <span class="absolute top-0 right-0 bg-red-600 text-white text-[10px] w-4 h-4 flex items-center justify-center rounded-full">{{ session.get('cart')|length }}</span>
                {% endif %}
            </a>
        </div>
    </header>

    <div class="h-16"></div>

    <!-- Flash Messages -->
    <div class="w-full max-w-[1600px] mx-auto px-4 mt-4">
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="p-4 mb-4 rounded-lg text-white font-medium shadow-md flex items-center justify-between animate-pulse
                {{ 'bg-green-600' if category == 'success' else 'bg-red-500' }}">
                <span><i class="fas {{ 'fa-check-circle' if category == 'success' else 'fa-exclamation-circle' }} mr-2"></i> {{ message }}</span>
                <button onclick="this.parentElement.remove()" class="text-white hover:text-gray-200"><i class="fas fa-times"></i></button>
              </div>
            {% endfor %}
          {% endif %}
        {% endwith %}
    </div>

    <!-- Main Content (Full Width Capable) -->
    <main class="flex-grow w-full max-w-[1600px] mx-auto px-4 py-6 md:py-8">
        {% block content %}{% endblock %}
    </main>

    <!-- Mobile Bottom Nav -->
    <div class="md:hidden fixed bottom-0 left-0 w-full bg-white border-t border-gray-200 flex justify-around py-3 z-50 pb-safe">
        <a href="/" class="flex flex-col items-center text-[10px] text-gray-500 hover:text-red-600">
            <i class="fas fa-home text-xl mb-1"></i> Home
        </a>
        <a href="/cart" class="flex flex-col items-center text-[10px] text-gray-500 hover:text-red-600">
            <i class="fas fa-search text-xl mb-1"></i> Cart
        </a>
        <a href="/profile" class="flex flex-col items-center text-[10px] text-gray-500 hover:text-red-600">
            <i class="fas fa-user text-xl mb-1"></i> Account
        </a>
    </div>
    <div class="h-16 md:hidden"></div> <!-- Spacer for bottom nav -->

    <script>
        window.onload = function() {
            const loader = document.getElementById('loader');
            loader.style.opacity = '0';
            setTimeout(() => { loader.style.display = 'none'; }, 500);
        };
    </script>
</body>
</html>
'''

HOME_HTML = '''
{% extends "layout" %}
{% block content %}
    
    <!-- Search Bar -->
    <div class="mb-8 max-w-3xl mx-auto relative z-10">
        <form action="/" method="GET" class="relative group">
            <input type="text" name="q" placeholder="Search mobiles, accessories..." 
                class="w-full pl-14 pr-6 py-4 rounded-full border-2 border-transparent shadow-lg group-hover:shadow-xl focus:border-gray-900 outline-none bg-white text-gray-800 transition-all">
            <i class="fas fa-search absolute left-6 top-4.5 text-gray-400 text-lg"></i>
        </form>
    </div>

    <!-- Promo Banner -->
    {% if promo_img %}
    <div class="mb-10 w-full rounded-3xl overflow-hidden shadow-2xl transform hover:scale-[1.01] transition duration-500">
        <a href="{{ promo_link }}">
            <img src="{{ promo_img }}" alt="Promo" class="w-full h-40 md:h-[450px] object-cover">
        </a>
    </div>
    {% endif %}

    <div class="flex items-center justify-between mb-6 border-b pb-4 border-gray-200">
        <h2 class="text-2xl md:text-3xl font-bold {{ theme.accent_text }}">Latest Collection</h2>
        <span class="text-gray-500 text-sm">{{ products|length }} Items</span>
    </div>
    
    {% if products %}
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4 md:gap-6">
        {% for product in products %}
        <div class="{{ theme.card_bg }} rounded-2xl shadow-sm hover:shadow-2xl hover:-translate-y-2 transition-all duration-300 overflow-hidden group flex flex-col h-full border border-gray-100">
            <a href="/product/{{ product.id }}" class="block relative w-full pt-[100%] bg-white overflow-hidden">
                <img src="{{ product.image_url }}" alt="{{ product.name }}" class="absolute top-0 left-0 w-full h-full object-contain p-6 group-hover:scale-110 transition-transform duration-500">
                {% if product.discount_price %}
                <span class="absolute top-3 right-3 bg-red-600 text-white text-[10px] font-bold px-2 py-1 rounded-md shadow-lg">-SALE-</span>
                {% endif %}
            </a>
            <div class="p-4 flex flex-col flex-grow">
                <h3 class="font-semibold text-gray-900 text-sm md:text-base mb-1 line-clamp-2">{{ product.name }}</h3>
                
                <div class="mt-auto pt-2">
                    <div class="flex flex-wrap items-baseline gap-2 mb-3">
                        {% if product.discount_price %}
                            <span class="text-lg font-bold text-red-600">Rs.{{ product.discount_price }}</span>
                            <span class="text-xs text-gray-400 line-through">Rs.{{ product.price }}</span>
                        {% else %}
                            <span class="text-lg font-bold text-gray-900">Rs.{{ product.price }}</span>
                        {% endif %}
                    </div>
                    <form action="/add_to_cart/{{ product.id }}" method="POST">
                        <button class="w-full {{ theme.btn_primary }} py-2.5 rounded-xl text-sm font-semibold shadow-md transform active:scale-95 transition-all">
                            Add to Cart <i class="fas fa-cart-plus ml-1"></i>
                        </button>
                    </form>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
    {% else %}
        <div class="text-center py-24 bg-white rounded-3xl border border-dashed border-gray-300">
            <i class="fas fa-box-open text-6xl text-gray-300 mb-4"></i>
            <p class="text-gray-500 text-lg">No products found matching your search.</p>
            <a href="/" class="text-blue-600 font-bold hover:underline mt-2 block">View All Products</a>
        </div>
    {% endif %}
{% endblock %}
'''

PRODUCT_DETAIL_HTML = '''
{% extends "layout" %}
{% block content %}
<div class="bg-white rounded-3xl shadow-xl overflow-hidden w-full border border-gray-100">
    <div class="md:flex">
        <div class="md:w-1/2 p-8 bg-white flex items-center justify-center border-r border-gray-100">
            <img src="{{ product.image_url }}" class="max-w-full max-h-[500px] object-contain hover:scale-105 transition-transform duration-500">
        </div>
        <div class="md:w-1/2 p-8 md:p-16 flex flex-col justify-center bg-white">
            <h1 class="text-3xl md:text-4xl font-bold text-gray-900 mb-4 leading-tight">{{ product.name }}</h1>
            
            <div class="flex items-center gap-4 mb-8 p-4 bg-gray-50 rounded-xl w-fit">
                {% if product.discount_price %}
                    <span class="text-4xl font-bold text-red-600">Rs.{{ product.discount_price }}</span>
                    <div class="flex flex-col">
                        <span class="text-sm text-gray-500 line-through">Rs.{{ product.price }}</span>
                        <span class="text-xs font-bold text-green-600">SAVE MONEY</span>
                    </div>
                {% else %}
                    <span class="text-4xl font-bold text-gray-900">Rs.{{ product.price }}</span>
                {% endif %}
            </div>

            <div class="prose text-gray-600 mb-10 leading-relaxed">
                <h3 class="font-bold text-gray-900 mb-3 uppercase text-sm tracking-wider">Description</h3>
                <p class="whitespace-pre-line">{{ product.description }}</p>
            </div>

            <form action="/add_to_cart/{{ product.id }}" method="POST" class="mt-auto">
                <button class="w-full md:w-auto {{ theme.btn_primary }} px-12 py-4 rounded-xl font-bold text-lg shadow-xl hover:shadow-2xl transform hover:-translate-y-1 transition-all flex items-center justify-center gap-3">
                    <span>Add to Cart</span>
                    <i class="fas fa-arrow-right"></i>
                </button>
            </form>
        </div>
    </div>
</div>
{% endblock %}
'''

LOGIN_HTML = '''
{% extends "layout" %}
{% block content %}
<div class="flex items-center justify-center min-h-[60vh]">
    <div class="w-full max-w-md bg-white p-10 rounded-3xl shadow-2xl border border-gray-100">
        <div class="text-center mb-8">
            <h2 class="text-3xl font-bold text-gray-900">Welcome Back</h2>
            <p class="text-gray-500 mt-2">Enter your details to login</p>
        </div>
        <form method="POST">
            <div class="space-y-5">
                <div>
                    <label class="text-xs font-bold text-gray-500 uppercase tracking-wide">Username / Email</label>
                    <input type="text" name="username" required class="w-full mt-2 border border-gray-300 rounded-xl bg-white p-3.5 focus:ring-2 focus:ring-black focus:border-transparent outline-none transition">
                </div>
                <div>
                    <label class="text-xs font-bold text-gray-500 uppercase tracking-wide">Password</label>
                    <input type="password" name="password" required class="w-full mt-2 border border-gray-300 rounded-xl bg-white p-3.5 focus:ring-2 focus:ring-black focus:border-transparent outline-none transition">
                </div>
            </div>
            <button type="submit" class="w-full mt-8 {{ theme.btn_primary }} py-4 rounded-xl font-bold shadow-lg hover:shadow-xl transition-all">Sign In</button>
        </form>
        <p class="text-center mt-8 text-sm text-gray-500">
            Don't have an account? <a href="/register" class="text-black font-bold hover:underline">Create one</a>
        </p>
    </div>
</div>
{% endblock %}
'''

REGISTER_HTML = '''
{% extends "layout" %}
{% block content %}
<div class="flex items-center justify-center min-h-[60vh]">
    <div class="w-full max-w-md bg-white p-10 rounded-3xl shadow-2xl border border-gray-100">
        <div class="text-center mb-8">
            <h2 class="text-3xl font-bold text-gray-900">Create Account</h2>
            <p class="text-gray-500 mt-2">Join us for premium shopping</p>
        </div>
        <form method="POST">
            <div class="space-y-4">
                <div>
                    <label class="text-xs font-bold text-gray-500 uppercase">Full Name</label>
                    <input type="text" name="full_name" required class="w-full mt-1 border border-gray-300 rounded-xl p-3.5 focus:ring-2 focus:ring-black outline-none">
                </div>
                <div>
                    <label class="text-xs font-bold text-gray-500 uppercase">Username / Email</label>
                    <input type="text" name="username" required class="w-full mt-1 border border-gray-300 rounded-xl p-3.5 focus:ring-2 focus:ring-black outline-none">
                </div>
                <div>
                    <label class="text-xs font-bold text-gray-500 uppercase">Password</label>
                    <input type="password" name="password" required class="w-full mt-1 border border-gray-300 rounded-xl p-3.5 focus:ring-2 focus:ring-black outline-none">
                </div>
            </div>
            <button type="submit" class="w-full mt-8 {{ theme.btn_primary }} py-4 rounded-xl font-bold shadow-lg">Sign Up</button>
        </form>
        <p class="text-center mt-8 text-sm text-gray-500">
            Already have an account? <a href="/login" class="text-black font-bold hover:underline">Login</a>
        </p>
    </div>
</div>
{% endblock %}
'''

PROFILE_HTML = '''
{% extends "layout" %}
{% block content %}
<div class="max-w-6xl mx-auto">
    <h1 class="text-3xl font-bold mb-6 text-gray-800">My Account</h1>
    
    <div class="grid md:grid-cols-3 gap-8">
        <!-- Profile Card -->
        <div class="bg-white p-6 rounded-2xl shadow-lg border border-gray-100 h-fit">
            <div class="flex flex-col items-center text-center mb-6">
                <div class="w-24 h-24 bg-gray-900 text-white rounded-full flex items-center justify-center text-4xl mb-4 shadow-lg">
                    <i class="fas fa-user"></i>
                </div>
                <h2 class="text-xl font-bold text-gray-900">{{ current_user.full_name or 'Valued Customer' }}</h2>
                <p class="text-sm text-gray-500">{{ current_user.username }}</p>
            </div>
            
            <form method="POST" class="space-y-4">
                <div>
                    <label class="text-xs font-bold text-gray-500 uppercase">Mobile Number</label>
                    <input type="tel" name="mobile" value="{{ current_user.mobile or '' }}" class="w-full border-gray-200 bg-gray-50 rounded-lg p-3 text-sm focus:ring-1 focus:ring-black outline-none">
                </div>
                <div>
                    <label class="text-xs font-bold text-gray-500 uppercase">Province</label>
                    <select name="province" class="w-full border-gray-200 bg-gray-50 rounded-lg p-3 text-sm focus:ring-1 focus:ring-black outline-none">
                        <option value="">Select Province</option>
                        {% for p in provinces %}
                        <option value="{{ p }}" {% if current_user.province == p %}selected{% endif %}>{{ p }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <label class="text-xs font-bold text-gray-500 uppercase">New Password (Optional)</label>
                    <input type="password" name="password" class="w-full border-gray-200 bg-gray-50 rounded-lg p-3 text-sm focus:ring-1 focus:ring-black outline-none">
                </div>
                <button type="submit" class="w-full bg-gray-900 text-white py-3 rounded-xl text-sm font-bold hover:bg-gray-800 transition">Save Changes</button>
            </form>
            
            <a href="/logout" class="block w-full mt-4 bg-red-50 text-red-600 hover:bg-red-600 hover:text-white text-center py-3 rounded-xl font-bold transition border border-red-100">
                Logout
            </a>
        </div>

        <!-- Orders Section -->
        <div class="md:col-span-2">
            <div class="bg-white rounded-2xl shadow-lg border border-gray-100 overflow-hidden">
                <div class="p-6 border-b border-gray-100">
                    <h3 class="text-xl font-bold text-gray-900">Order History</h3>
                </div>
                
                {% if my_orders %}
                    <div class="divide-y divide-gray-100">
                    {% for order in my_orders %}
                        <div class="p-6 hover:bg-gray-50 transition">
                            <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-3">
                                <div>
                                    <div class="flex items-center gap-3">
                                        <span class="bg-gray-100 text-gray-600 px-2 py-1 rounded text-xs font-bold">#{{ order.id }}</span>
                                        <span class="text-sm text-gray-500">{{ order.created_at[:10] }}</span>
                                    </div>
                                    <h4 class="font-bold text-gray-800 mt-2 text-lg">Rs. {{ order.total_amount }}</h4>
                                </div>
                                <div class="flex items-center gap-2">
                                    <span class="px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide
                                        {{ 'bg-green-100 text-green-700' if order.status == 'Delivered' else 'bg-orange-100 text-orange-700' }}">
                                        {{ order.status }}
                                    </span>
                                    <!-- View Details Button -->
                                    <button onclick="openModal('{{ order.id }}', '{{ order.items_summary|replace("'", "") }}', '{{ order.total_amount }}', '{{ order.status }}', '{{ order.created_at }}', '{{ order.address|replace("'", "") }}')" 
                                        class="bg-blue-50 text-blue-600 px-4 py-2 rounded-lg text-xs font-bold hover:bg-blue-600 hover:text-white transition">
                                        View Details
                                    </button>
                                </div>
                            </div>
                            <p class="text-sm text-gray-600 truncate">{{ order.items_summary }}</p>
                        </div>
                    {% endfor %}
                    </div>
                {% else %}
                    <div class="p-12 text-center text-gray-400">
                        <i class="fas fa-shopping-bag text-4xl mb-3"></i>
                        <p>No orders placed yet.</p>
                    </div>
                {% endif %}
            </div>
        </div>
    </div>
</div>

<!-- ORDER DETAILS MODAL (Full Screen Overlay) -->
<div id="orderModal" class="modal opacity-0 pointer-events-none fixed w-full h-full top-0 left-0 flex items-center justify-center z-50">
    <div class="modal-overlay absolute w-full h-full bg-gray-900 opacity-50" onclick="closeModal()"></div>
    
    <div class="modal-container bg-white w-11/12 md:max-w-md mx-auto rounded-2xl shadow-2xl z-50 overflow-y-auto animate-bounce-in">
        <div class="relative py-8 px-6">
            <!-- Close X -->
            <div class="absolute top-4 right-4 cursor-pointer z-50" onclick="closeModal()">
                <i class="fas fa-times text-gray-500 hover:text-red-500 text-xl"></i>
            </div>
            
            <div class="text-center mb-6">
                <h3 class="text-2xl font-bold text-gray-900" id="modalTitle">Order Details</h3>
                <p class="text-sm text-gray-500" id="modalDate"></p>
            </div>

            <div class="space-y-4 bg-gray-50 p-4 rounded-xl border border-gray-100">
                <div class="flex justify-between border-b pb-2">
                    <span class="text-gray-500 text-sm">Status</span>
                    <span class="font-bold text-gray-800" id="modalStatus"></span>
                </div>
                <div class="flex justify-between border-b pb-2">
                    <span class="text-gray-500 text-sm">Total Amount</span>
                    <span class="font-bold text-red-600 text-lg" id="modalTotal"></span>
                </div>
                <div>
                    <span class="text-gray-500 text-sm block mb-1">Delivery Address</span>
                    <p class="text-sm font-medium text-gray-800" id="modalAddress"></p>
                </div>
            </div>

            <div class="mt-6">
                <h4 class="text-sm font-bold text-gray-500 uppercase mb-2">Items Purchased</h4>
                <div class="bg-white border border-gray-200 rounded-xl p-4 text-sm text-gray-700 leading-relaxed" id="modalItems">
                </div>
            </div>

            <button onclick="closeModal()" class="w-full bg-gray-900 text-white py-3 rounded-xl font-bold mt-6">Close</button>
        </div>
    </div>
</div>

<script>
    function openModal(id, items, total, status, date, address) {
        document.getElementById('modalTitle').innerText = 'Order #' + id;
        document.getElementById('modalDate').innerText = date;
        document.getElementById('modalStatus').innerText = status;
        document.getElementById('modalTotal').innerText = 'Rs. ' + total;
        document.getElementById('modalAddress').innerText = address;
        document.getElementById('modalItems').innerText = items;
        
        const modal = document.getElementById('orderModal');
        modal.classList.remove('opacity-0', 'pointer-events-none');
        document.body.classList.add('modal-active');
    }

    function closeModal() {
        const modal = document.getElementById('orderModal');
        modal.classList.add('opacity-0', 'pointer-events-none');
        document.body.classList.remove('modal-active');
    }
</script>
{% endblock %}
'''

CART_HTML = '''
{% extends "layout" %}
{% block content %}
<div class="max-w-5xl mx-auto">
    <h2 class="text-3xl font-bold mb-8 text-gray-900">Your Shopping Cart</h2>
    {% if cart_items %}
        <div class="flex flex-col lg:flex-row gap-10">
            <div class="lg:w-2/3">
                <div class="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
                    {% for item in cart_items %}
                    <div class="flex items-center p-5 border-b border-gray-100 last:border-0 hover:bg-gray-50 transition relative">
                        <div class="w-24 h-24 bg-gray-100 rounded-xl flex-shrink-0 mr-5 border border-gray-200">
                            <img src="{{ item.image_url }}" class="w-full h-full object-contain p-2">
                        </div>
                        <div class="flex-grow pr-10">
                            <h3 class="font-bold text-gray-800 text-lg">{{ item.name }}</h3>
                            <div class="mt-1">
                                {% if item.discount_price %}
                                    <span class="text-red-600 font-bold">Rs.{{ item.discount_price }}</span>
                                    <span class="text-xs text-gray-400 line-through ml-2">Rs.{{ item.price }}</span>
                                {% else %}
                                    <span class="font-bold text-gray-900">Rs.{{ item.price }}</span>
                                {% endif %}
                            </div>
                        </div>
                        <a href="/remove_from_cart/{{ loop.index0 }}" class="absolute right-4 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center rounded-full bg-red-50 text-red-500 hover:bg-red-500 hover:text-white transition shadow-sm">
                            <i class="fas fa-trash-alt"></i>
                        </a>
                    </div>
                    {% endfor %}
                </div>
            </div>
            
            <div class="lg:w-1/3">
                <div class="bg-white p-8 rounded-2xl shadow-xl border border-gray-100 sticky top-24">
                    <h3 class="font-bold text-xl mb-6 border-b pb-4">Order Summary</h3>
                    <div class="flex justify-between mb-3 text-gray-600">
                        <span>Subtotal</span>
                        <span>Rs.{{ total }}</span>
                    </div>
                    <div class="flex justify-between mb-6 text-gray-600">
                        <span>Delivery Fee</span>
                        <span class="text-green-600 font-bold">Free</span>
                    </div>
                    <div class="border-t pt-6 flex justify-between items-end mb-8">
                        <span class="font-bold text-lg text-gray-800">Total</span>
                        <span class="font-bold text-3xl text-gray-900">Rs.{{ total }}</span>
                    </div>
                    <a href="/checkout" class="block w-full {{ theme.btn_primary }} text-center py-4 rounded-xl font-bold text-lg shadow-lg hover:scale-[1.02] transition-transform">
                        Proceed to Checkout
                    </a>
                </div>
            </div>
        </div>
    {% else %}
        <div class="text-center py-32 bg-white rounded-3xl shadow-sm border border-gray-200">
            <div class="bg-gray-50 w-24 h-24 rounded-full flex items-center justify-center mx-auto mb-6">
                <i class="fas fa-shopping-cart text-4xl text-gray-300"></i>
            </div>
            <h3 class="text-xl font-bold text-gray-800 mb-2">Your cart is empty</h3>
            <p class="text-gray-500 mb-8">Looks like you haven't added anything yet.</p>
            <a href="/" class="inline-block bg-black text-white px-8 py-3 rounded-xl font-bold hover:bg-gray-800 transition">Start Shopping</a>
        </div>
    {% endif %}
</div>
{% endblock %}
'''

CHECKOUT_HTML = '''
{% extends "layout" %}
{% block content %}
<div class="max-w-6xl mx-auto">
    <h2 class="text-3xl font-bold mb-8 text-gray-900">Checkout</h2>
    <div class="flex flex-col md:flex-row gap-10">
        
        <!-- Payment Methods -->
        <div class="md:w-1/2 order-2 md:order-1">
            <div class="bg-white p-8 rounded-3xl shadow-lg border border-gray-100">
                <h3 class="font-bold text-xl text-gray-800 mb-6">Payment Method</h3>
                <div class="space-y-4">
                    {% for method in payment_methods %}
                    <label class="block cursor-pointer">
                        <input type="radio" name="payment" class="peer sr-only" checked>
                        <div class="border-2 border-gray-100 rounded-2xl p-5 hover:border-gray-300 peer-checked:border-black peer-checked:bg-gray-50 transition flex justify-between items-center">
                            <div>
                                <h4 class="font-bold text-gray-800 text-lg">{{ method.method_name }}</h4>
                                <p class="text-sm bg-white border px-2 py-1 rounded mt-2 font-mono inline-block text-gray-600">{{ method.account_number }}</p>
                            </div>
                            {% if method.qr_image %}
                            <img src="{{ method.qr_image }}" class="w-20 h-20 object-contain bg-white rounded-lg p-1 border">
                            {% endif %}
                        </div>
                    </label>
                    {% endfor %}
                    
                    <label class="block cursor-pointer">
                        <input type="radio" name="payment" class="peer sr-only">
                        <div class="border-2 border-gray-100 rounded-2xl p-5 hover:border-gray-300 peer-checked:border-green-500 peer-checked:bg-green-50 transition">
                             <h4 class="font-bold text-green-800 flex items-center gap-2">
                                <i class="fas fa-money-bill-wave"></i> Cash on Delivery
                             </h4>
                             <p class="text-sm text-green-700 mt-1 ml-6">Pay with cash upon arrival.</p>
                        </div>
                    </label>
                </div>
                
                <div class="mt-8 pt-6 border-t border-gray-100">
                    <div class="flex justify-between items-center">
                         <span class="text-gray-600 font-medium">Total Amount To Pay:</span>
                         <span class="text-3xl font-bold text-red-600">Rs.{{ total }}</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Form -->
        <div class="md:w-1/2 order-1 md:order-2">
            <form method="POST" class="bg-white p-8 rounded-3xl shadow-xl border border-gray-200 relative overflow-hidden">
                <div class="absolute top-0 left-0 w-full h-2 bg-gray-900"></div>
                <h3 class="font-bold text-xl mb-6">Shipping Details</h3>
                
                <div class="space-y-5">
                    <div>
                        <label class="block text-xs font-bold text-gray-500 uppercase mb-1">Full Name</label>
                        <input type="text" name="full_name" value="{{ current_user.full_name or '' }}" required class="w-full border border-gray-300 rounded-xl bg-gray-50 p-3.5 focus:ring-2 focus:ring-black outline-none transition">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-gray-500 uppercase mb-1">Mobile Number</label>
                        <input type="tel" name="mobile" value="{{ current_user.mobile or '' }}" required pattern="[0-9]{10}" class="w-full border border-gray-300 rounded-xl bg-gray-50 p-3.5 focus:ring-2 focus:ring-black outline-none transition">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-gray-500 uppercase mb-1">Province</label>
                        <select name="province" required class="w-full border border-gray-300 rounded-xl bg-gray-50 p-3.5 focus:ring-2 focus:ring-black outline-none transition">
                            <option value="">Select Province</option>
                            {% for p in provinces %}
                            <option value="{{ p }}" {% if current_user.province == p %}selected{% endif %}>{{ p }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-gray-500 uppercase mb-1">Delivery Address</label>
                        <textarea name="address" required rows="3" placeholder="City, Street Name, House No..." class="w-full border border-gray-300 rounded-xl bg-gray-50 p-3.5 focus:ring-2 focus:ring-black outline-none transition"></textarea>
                    </div>
                </div>

                <button type="submit" class="w-full mt-8 {{ theme.btn_primary }} py-4 rounded-xl font-bold text-lg shadow-xl hover:scale-[1.01] transition-transform flex justify-center items-center gap-2">
                    <i class="fas fa-check-circle"></i> Confirm Order
                </button>
            </form>
        </div>
    </div>
</div>
{% endblock %}
'''

ADMIN_HTML = '''
{% extends "layout" %}
{% block content %}
<div class="flex flex-col lg:flex-row min-h-[700px] bg-white rounded-2xl shadow-2xl overflow-hidden border border-gray-200">
    
    <!-- Admin Sidebar -->
    <div class="lg:w-72 bg-gray-900 text-gray-300 flex-shrink-0 p-6">
        <h2 class="text-white font-bold text-2xl mb-10 px-2 flex items-center gap-3">
            <i class="fas fa-user-shield text-red-500"></i> Admin Panel
        </h2>
        <nav class="space-y-2">
            <button onclick="showTab('dashboard')" id="tab-dashboard" class="w-full text-left px-5 py-4 rounded-xl hover:bg-gray-800 transition font-medium flex items-center gap-3 text-white bg-gray-800 border-l-4 border-red-500">
                <i class="fas fa-tachometer-alt w-5"></i> Dashboard
            </button>
            <button onclick="showTab('orders')" id="tab-orders" class="w-full text-left px-5 py-4 rounded-xl hover:bg-gray-800 transition font-medium flex items-center gap-3">
                <i class="fas fa-shopping-bag w-5"></i> Orders
            </button>
            <button onclick="showTab('products')" id="tab-products" class="w-full text-left px-5 py-4 rounded-xl hover:bg-gray-800 transition font-medium flex items-center gap-3">
                <i class="fas fa-box w-5"></i> Products
            </button>
            <button onclick="showTab('settings')" id="tab-settings" class="w-full text-left px-5 py-4 rounded-xl hover:bg-gray-800 transition font-medium flex items-center gap-3">
                <i class="fas fa-cog w-5"></i> Settings
            </button>
        </nav>
        <div class="mt-auto pt-10">
            <a href="/logout" class="flex items-center gap-3 px-5 text-gray-400 hover:text-white transition">
                <i class="fas fa-sign-out-alt"></i> Logout
            </a>
        </div>
    </div>

    <!-- Admin Content Area -->
    <div class="flex-grow p-6 lg:p-10 bg-gray-50 overflow-y-auto h-screen pb-24">
        
        <!-- DASHBOARD OVERVIEW TAB -->
        <div id="dashboard-content">
            <h3 class="text-2xl font-bold text-gray-800 mb-6">Overview</h3>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
                <!-- Card 1: Users -->
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 flex items-center gap-4">
                    <div class="w-14 h-14 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-2xl">
                        <i class="fas fa-users"></i>
                    </div>
                    <div>
                        <p class="text-sm text-gray-500 font-bold uppercase">Total Users</p>
                        <h4 class="text-3xl font-bold text-gray-900">{{ stats.users }}</h4>
                    </div>
                </div>
                <!-- Card 2: Earnings -->
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 flex items-center gap-4">
                    <div class="w-14 h-14 rounded-full bg-green-100 text-green-600 flex items-center justify-center text-2xl">
                        <i class="fas fa-wallet"></i>
                    </div>
                    <div>
                        <p class="text-sm text-gray-500 font-bold uppercase">Total Earnings</p>
                        <h4 class="text-3xl font-bold text-gray-900">Rs. {{ stats.earnings }}</h4>
                    </div>
                </div>
                <!-- Card 3: Orders -->
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 flex items-center gap-4">
                    <div class="w-14 h-14 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center text-2xl">
                        <i class="fas fa-shopping-cart"></i>
                    </div>
                    <div>
                        <p class="text-sm text-gray-500 font-bold uppercase">Total Orders</p>
                        <h4 class="text-3xl font-bold text-gray-900">{{ stats.orders_count }}</h4>
                    </div>
                </div>
            </div>
            
            <div class="bg-white p-8 rounded-2xl shadow-sm border border-gray-100">
                <h4 class="font-bold text-lg mb-4">Recent Activity</h4>
                <p class="text-gray-500">Check the Orders tab for detailed lists.</p>
            </div>
        </div>

        <!-- ORDERS TAB -->
        <div id="orders-content" class="hidden">
            <h3 class="text-2xl font-bold text-gray-800 mb-6">Order Management</h3>
            <div class="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
                <div class="overflow-x-auto">
                    <table class="w-full text-sm text-left">
                        <thead class="bg-gray-100 text-gray-600 uppercase text-xs font-bold">
                            <tr>
                                <th class="px-6 py-4">ID</th>
                                <th class="px-6 py-4">Customer</th>
                                <th class="px-6 py-4">Total</th>
                                <th class="px-6 py-4">Status</th>
                                <th class="px-6 py-4 text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-100">
                            {% for order in orders %}
                            <tr class="hover:bg-gray-50 transition">
                                <td class="px-6 py-4 font-bold text-gray-900">#{{ order.id }}</td>
                                <td class="px-6 py-4">
                                    <div class="font-bold text-gray-800">{{ order.full_name }}</div>
                                    <div class="text-xs text-gray-500">{{ order.mobile }}</div>
                                    <div class="text-xs text-gray-400 truncate w-40" title="{{ order.address }}">{{ order.address }}</div>
                                </td>
                                <td class="px-6 py-4 font-bold text-red-600">Rs.{{ order.total_amount }}</td>
                                <td class="px-6 py-4">
                                    <span class="px-3 py-1 rounded-full text-xs font-bold uppercase
                                    {{ 'bg-green-100 text-green-700' if order.status == 'Delivered' else 'bg-orange-100 text-orange-700' }}">
                                        {{ order.status }}
                                    </span>
                                </td>
                                <td class="px-6 py-4 text-right">
                                    <div class="flex justify-end gap-2">
                                        {% if order.status != 'Delivered' %}
                                        <a href="/admin/order/status/{{ order.id }}/Delivered" class="bg-green-50 text-green-600 border border-green-200 w-8 h-8 flex items-center justify-center rounded-lg hover:bg-green-500 hover:text-white transition" title="Mark Delivered"><i class="fas fa-check"></i></a>
                                        {% else %}
                                        <a href="/admin/order/status/{{ order.id }}/Pending" class="bg-orange-50 text-orange-600 border border-orange-200 w-8 h-8 flex items-center justify-center rounded-lg hover:bg-orange-500 hover:text-white transition" title="Mark Pending"><i class="fas fa-undo"></i></a>
                                        {% endif %}
                                        <a href="/admin/order/delete/{{ order.id }}" onclick="return confirm('Delete this order?')" class="bg-red-50 text-red-600 border border-red-200 w-8 h-8 flex items-center justify-center rounded-lg hover:bg-red-500 hover:text-white transition"><i class="fas fa-trash"></i></a>
                                    </div>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- PRODUCTS TAB -->
        <div id="products-content" class="hidden">
            <h3 class="text-2xl font-bold text-gray-800 mb-6">Manage Products</h3>
            
            <form action="/admin/product/add" method="POST" enctype="multipart/form-data" class="bg-white p-6 rounded-2xl shadow-sm mb-8 border border-gray-200">
                <h4 class="font-bold mb-4 text-sm uppercase text-gray-500">Add New Product</h4>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-5 mb-4">
                    <input type="text" name="name" placeholder="Product Name" required class="border border-gray-300 p-3 rounded-xl outline-none focus:border-gray-900">
                    <input type="number" name="price" placeholder="Price" required class="border border-gray-300 p-3 rounded-xl outline-none focus:border-gray-900">
                    <input type="number" name="discount_price" placeholder="Sale Price (Optional)" class="border border-gray-300 p-3 rounded-xl outline-none focus:border-gray-900">
                    <input type="file" name="image" required class="border border-gray-300 p-2 rounded-xl text-sm bg-white">
                </div>
                <textarea name="description" placeholder="Description" class="w-full border border-gray-300 p-3 rounded-xl mb-4 outline-none focus:border-gray-900" rows="3"></textarea>
                <button type="submit" class="bg-blue-600 text-white px-8 py-3 rounded-xl font-bold hover:bg-blue-700 shadow-lg transition">Add Product</button>
            </form>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-6">
                {% for p in products %}
                <div class="bg-white p-4 rounded-2xl shadow-sm border border-gray-100 relative group hover:shadow-lg transition">
                    <img src="{{ p.image_url }}" class="w-full h-40 object-contain mb-3 rounded-lg">
                    <h4 class="font-bold text-gray-800 truncate">{{ p.name }}</h4>
                    <p class="text-sm text-gray-500">Rs.{{ p.price }}</p>
                    <a href="/admin/product/delete/{{ p.id }}" onclick="return confirm('Delete?')" class="absolute top-3 right-3 bg-white text-red-500 w-8 h-8 flex items-center justify-center rounded-full shadow-md hover:bg-red-500 hover:text-white transition"><i class="fas fa-trash"></i></a>
                </div>
                {% endfor %}
            </div>
        </div>

        <!-- SETTINGS TAB -->
        <div id="settings-content" class="hidden">
            <h3 class="text-2xl font-bold text-gray-800 mb-6">Site Settings</h3>
            <div class="grid md:grid-cols-2 gap-8">
                <!-- Theme Config -->
                <div class="space-y-6">
                    <div class="bg-white p-8 rounded-2xl shadow-sm border border-gray-200">
                        <h4 class="font-bold text-lg mb-6 border-b pb-2">Appearance</h4>
                        <form action="/admin/settings" method="POST" enctype="multipart/form-data" class="space-y-5">
                            <div>
                                <label class="text-xs font-bold text-gray-500 uppercase">Store Name</label>
                                <input type="text" name="site_title" value="{{ settings.get('site_title', '') }}" class="w-full border p-3 rounded-xl mt-1">
                            </div>
                            <div>
                                <label class="text-xs font-bold text-gray-500 uppercase">Color Theme</label>
                                <select name="theme" class="w-full border p-3 rounded-xl mt-1 bg-white">
                                    <option value="Modern White" {% if settings.get('theme') == 'Modern White' %}selected{% endif %}>Modern White</option>
                                    <option value="Dashain Festival" {% if settings.get('theme') == 'Dashain Festival' %}selected{% endif %}>Dashain (Red)</option>
                                    <option value="Tihar Night" {% if settings.get('theme') == 'Tihar Night' %}selected{% endif %}>Tihar (Dark)</option>
                                </select>
                            </div>
                            <div class="border-t pt-5">
                                <label class="text-xs font-bold text-gray-500 uppercase block mb-2">Promo Banner</label>
                                <input type="file" name="promo_image" class="w-full text-sm mb-3 border p-2 rounded-lg">
                                <input type="text" name="promo_link" value="{{ settings.get('promo_link', '') }}" placeholder="Link URL (e.g. /product/1)" class="w-full border p-3 rounded-xl text-sm">
                            </div>
                            <div class="flex gap-3 pt-2">
                                <button type="submit" class="bg-gray-900 text-white px-6 py-3 rounded-xl text-sm font-bold hover:bg-black">Save Changes</button>
                                <a href="/admin/settings/remove_banner" class="bg-red-50 text-red-600 px-6 py-3 rounded-xl text-sm font-bold hover:bg-red-100">Remove Banner</a>
                            </div>
                        </form>
                    </div>
                </div>

                <!-- Payment Methods -->
                <div class="bg-white p-8 rounded-2xl shadow-sm border border-gray-200">
                    <h4 class="font-bold text-lg mb-6 border-b pb-2">Payment Methods</h4>
                    <form action="/admin/payment/add" method="POST" enctype="multipart/form-data" class="space-y-4 mb-6">
                        <input type="text" name="method_name" placeholder="Name (e.g. eSewa)" required class="w-full border p-3 rounded-xl text-sm">
                        <input type="text" name="account_number" placeholder="Account Number" required class="w-full border p-3 rounded-xl text-sm">
                        <div class="border p-2 rounded-xl">
                            <label class="text-xs text-gray-500 block mb-1">QR Code Image</label>
                            <input type="file" name="qr_image" class="w-full text-xs">
                        </div>
                        <button type="submit" class="bg-green-600 text-white px-6 py-3 rounded-xl text-sm font-bold w-full hover:bg-green-700">Add Payment Method</button>
                    </form>
                    <div class="space-y-3">
                        {% for pm in payment_methods %}
                        <div class="flex justify-between items-center bg-gray-50 p-4 rounded-xl border border-gray-200">
                            <div>
                                <span class="font-bold block text-gray-800">{{ pm.method_name }}</span>
                                <span class="text-xs text-gray-500">{{ pm.account_number }}</span>
                            </div>
                            <a href="/admin/payment/delete/{{ pm.id }}" class="text-red-500 bg-white w-8 h-8 flex items-center justify-center rounded-full shadow-sm hover:bg-red-500 hover:text-white transition"><i class="fas fa-times"></i></a>
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>
        </div>

    </div>
</div>

<script>
    function showTab(tabName) {
        // Hide all
        ['dashboard', 'orders', 'products', 'settings'].forEach(t => {
            document.getElementById(t + '-content').classList.add('hidden');
            const btn = document.getElementById('tab-' + t);
            btn.classList.remove('bg-gray-800', 'text-white', 'border-l-4', 'border-red-500');
            btn.classList.add('text-gray-400');
        });

        // Show Selected
        document.getElementById(tabName + '-content').classList.remove('hidden');
        const activeBtn = document.getElementById('tab-' + tabName);
        activeBtn.classList.add('bg-gray-800', 'text-white', 'border-l-4', 'border-red-500');
        activeBtn.classList.remove('text-gray-400');
    }
</script>
{% endblock %}
'''

# ==========================================
# APPLICATION LOGIC
# ==========================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('login'))
        db = get_db()
        user = db.execute('SELECT is_admin FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if not user or not user['is_admin']:
            flash("Access denied.", "error")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def save_image(file_obj):
    if file_obj and file_obj.filename:
        filename = secure_filename(str(int(time.time())) + "_" + file_obj.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file_obj.save(file_path)
        return f"/static/uploads/{filename}"
    return None

@app.context_processor
def inject_globals():
    db = get_db()
    user = None
    if 'user_id' in session:
        user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    # Theme Logic
    theme_row = db.execute("SELECT value FROM settings WHERE key='theme'").fetchone()
    theme_key = theme_row['value'] if theme_row else "Modern White"
    if theme_key not in THEMES: theme_key = "Modern White"
    
    # Title Logic
    title_row = db.execute("SELECT value FROM settings WHERE key='site_title'").fetchone()
    site_title = title_row['value'] if title_row else "AtoZ Store"

    return dict(current_user=user, theme=THEMES[theme_key], site_title=site_title, provinces=PROVINCES)

# Register Templates
app.jinja_loader = DictLoader({
    'layout': LAYOUT_HTML,
    'home': HOME_HTML,
    'product_detail': PRODUCT_DETAIL_HTML,
    'login': LOGIN_HTML,
    'register': REGISTER_HTML,
    'profile': PROFILE_HTML,
    'cart': CART_HTML,
    'checkout': CHECKOUT_HTML,
    'admin': ADMIN_HTML
})

# --- Routes ---

@app.route('/')
def home():
    db = get_db()
    search = request.args.get('q', '')
    if search:
        products = db.execute("SELECT * FROM products WHERE name LIKE ?", ('%'+search+'%',)).fetchall()
    else:
        products = db.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    
    promo_img = db.execute("SELECT value FROM settings WHERE key='promo_image'").fetchone()
    promo_link = db.execute("SELECT value FROM settings WHERE key='promo_link'").fetchone()
    
    return render_template('home', products=products, 
                          promo_img=promo_img['value'] if promo_img else None,
                          promo_link=promo_link['value'] if promo_link else "#")

@app.route('/product/<int:id>')
def product_detail(id):
    product = get_db().execute("SELECT * FROM products WHERE id=?", (id,)).fetchone()
    if not product: return redirect('/')
    return render_template('product_detail', product=product)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = get_db().execute('SELECT * FROM users WHERE username = ?', (request.form['username'],)).fetchone()
        if user and check_password_hash(user['password'], request.form['password']):
            session['user_id'] = user['id']
            return redirect(url_for('home'))
        flash('Invalid Username or Password', 'error')
    return render_template('login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        hashed = generate_password_hash(request.form['password'])
        try:
            db = get_db()
            db.execute("INSERT INTO users (username, password, full_name) VALUES (?, ?, ?)",
                       (request.form['username'], hashed, request.form['full_name']))
            db.commit()
            flash('Account created! Login now.', 'success')
            return redirect('/login')
        except:
            flash('Username already exists.', 'error')
    return render_template('register')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Logged out successfully.', 'success')
    return redirect('/')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    db = get_db()
    if request.method == 'POST':
        uid = session['user_id']
        mobile = request.form.get('mobile')
        province = request.form.get('province')
        pwd = request.form.get('password')
        
        if pwd:
            h = generate_password_hash(pwd)
            db.execute("UPDATE users SET mobile=?, province=?, password=? WHERE id=?", (mobile, province, h, uid))
        else:
            db.execute("UPDATE users SET mobile=?, province=? WHERE id=?", (mobile, province, uid))
        db.commit()
        flash('Profile Updated Successfully', 'success')
        return redirect('/profile')
        
    orders = db.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (session['user_id'],)).fetchall()
    return render_template('profile', my_orders=orders)

@app.route('/add_to_cart/<int:id>', methods=['POST'])
def add_to_cart(id):
    if 'cart' not in session: session['cart'] = []
    cart = session['cart']
    cart.append(id)
    session['cart'] = cart
    flash('Added to cart', 'success')
    return redirect(request.referrer)

@app.route('/remove_from_cart/<int:index>')
def remove_from_cart(index):
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        cart.pop(index)
        session['cart'] = cart
    return redirect('/cart')

@app.route('/cart')
def cart():
    ids = session.get('cart', [])
    items = []
    total = 0
    if ids:
        db = get_db()
        placeholders = ','.join('?' * len(ids))
        products = db.execute(f"SELECT * FROM products WHERE id IN ({placeholders})", ids).fetchall()
        pmap = {p['id']: p for p in products}
        for i in ids:
            if i in pmap:
                items.append(pmap[i])
                total += (pmap[i]['discount_price'] or pmap[i]['price'])
    return render_template('cart', cart_items=items, total=total)

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    db = get_db()
    ids = session.get('cart', [])
    if not ids: return redirect('/')
    
    # Calculate Total
    total = 0
    names = []
    placeholders = ','.join('?' * len(ids))
    products = db.execute(f"SELECT id, name, price, discount_price FROM products WHERE id IN ({placeholders})", ids).fetchall()
    pmap = {p['id']: p for p in products}
    
    for i in ids:
        if i in pmap:
            p = pmap[i]
            total += (p['discount_price'] or p['price'])
            names.append(p['name'])
    
    if request.method == 'POST':
        full_name = request.form['full_name']
        mobile = request.form['mobile']
        addr = f"{request.form['address']}, {request.form['province']}"
        
        db.execute('''INSERT INTO orders (user_id, full_name, mobile, address, total_amount, items_summary)
                      VALUES (?, ?, ?, ?, ?, ?)''',
                   (session['user_id'], full_name, mobile, addr, total, ", ".join(names)))
        
        # Update User Info
        db.execute("UPDATE users SET full_name=?, mobile=?, province=? WHERE id=?", 
                   (full_name, mobile, request.form['province'], session['user_id']))
        
        db.commit()
        session.pop('cart', None)
        flash('Order placed! We will contact you shortly.', 'success')
        return redirect('/profile')

    methods = db.execute("SELECT * FROM payment_methods").fetchall()
    return render_template('checkout', total=total, payment_methods=methods)

# --- Admin Routes ---
@app.route('/admin')
@admin_required
def admin():
    db = get_db()
    
    # Statistics for Dashboard
    user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    order_count = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    total_earnings = db.execute("SELECT SUM(total_amount) FROM orders").fetchone()[0]
    
    stats = {
        "users": user_count,
        "orders_count": order_count,
        "earnings": total_earnings if total_earnings else 0
    }

    return render_template('admin', 
                          products=db.execute("SELECT * FROM products ORDER BY id DESC").fetchall(),
                          orders=db.execute("SELECT * FROM orders ORDER BY id DESC").fetchall(),
                          settings={r['key']: r['value'] for r in db.execute("SELECT * FROM settings").fetchall()},
                          payment_methods=db.execute("SELECT * FROM payment_methods").fetchall(),
                          stats=stats)

@app.route('/admin/product/add', methods=['POST'])
@admin_required
def add_product():
    img_url = save_image(request.files.get('image'))
    disc = request.form.get('discount_price')
    disc = float(disc) if disc else None
    
    get_db().execute("INSERT INTO products (name, price, discount_price, description, image_url) VALUES (?,?,?,?,?)",
                     (request.form['name'], request.form['price'], disc, request.form['description'], img_url))
    get_db().commit()
    return redirect('/admin')

@app.route('/admin/product/delete/<int:id>')
@admin_required
def delete_product(id):
    get_db().execute("DELETE FROM products WHERE id=?", (id,))
    get_db().commit()
    return redirect('/admin')

@app.route('/admin/order/status/<int:id>/<status>')
@admin_required
def order_status(id, status):
    get_db().execute("UPDATE orders SET status=? WHERE id=?", (status, id))
    get_db().commit()
    return redirect('/admin')

@app.route('/admin/order/delete/<int:id>')
@admin_required
def delete_order(id):
    get_db().execute("DELETE FROM orders WHERE id=?", (id,))
    get_db().commit()
    return redirect('/admin')

@app.route('/admin/settings', methods=['POST'])
@admin_required
def settings():
    db = get_db()
    db.execute("REPLACE INTO settings (key, value) VALUES ('site_title', ?)", (request.form['site_title'],))
    db.execute("REPLACE INTO settings (key, value) VALUES ('theme', ?)", (request.form['theme'],))
    db.execute("REPLACE INTO settings (key, value) VALUES ('promo_link', ?)", (request.form['promo_link'],))
    
    f = request.files.get('promo_image')
    if f and f.filename:
        url = save_image(f)
        db.execute("REPLACE INTO settings (key, value) VALUES ('promo_image', ?)", (url,))
    
    db.commit()
    flash('Settings Saved', 'success')
    return redirect('/admin')

@app.route('/admin/settings/remove_banner')
@admin_required
def remove_banner():
    get_db().execute("DELETE FROM settings WHERE key='promo_image'")
    get_db().commit()
    flash('Banner Removed', 'success')
    return redirect('/admin')

@app.route('/admin/payment/add', methods=['POST'])
@admin_required
def add_payment():
    url = save_image(request.files.get('qr_image'))
    get_db().execute("INSERT INTO payment_methods (method_name, account_number, qr_image) VALUES (?,?,?)",
                     (request.form['method_name'], request.form['account_number'], url))
    get_db().commit()
    return redirect('/admin')

@app.route('/admin/payment/delete/<int:id>')
@admin_required
def delete_payment(id):
    get_db().execute("DELETE FROM payment_methods WHERE id=?", (id,))
    get_db().commit()
    return redirect('/admin')

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)⁷
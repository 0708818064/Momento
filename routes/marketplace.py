# routes/marketplace.py

from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, send_from_directory, abort, current_app # Added current_app for logging
)
from flask_login import login_required, current_user, login_user
# --- Assuming models are correctly defined ---
from core.marketplace.models import (
    Seller, Product, Buyer, Payment, PaymentStatus, PaymentMethod,
    Order, DeliveryStatus
)
from core.auth.models import User # Assuming User model is here
# --- Assuming db_session is correctly configured ---
from core.database import db_session
# --- Assuming these exist and work ---
from core.challenges.challenge_manager import ChallengeManager
# --- Remove email verification import ---
# from core.email.service import send_verification_email
from core.payment.service import process_payment
# --- M-Pesa Integration ---
from core.payments.mpesa import mpesa_client

# --- Other necessary imports ---
from flask_wtf.csrf import CSRFProtect # Recommended to enable
from functools import wraps
import os
import traceback # For detailed error logging
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
import uuid
import json
import stripe # If used directly
from uuid import uuid4
import magic
from datetime import datetime
from sqlalchemy import func # For potential aggregate queries like total_sales

# --- Define Blueprint FIRST ---
marketplace_bp = Blueprint('marketplace', __name__, url_prefix='/marketplace')

# --- Other Setup (Constants, Helpers, Manager Instances) ---
# Consider moving these to app config if not already there
UPLOAD_FOLDER = 'uploads/products'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

# Configure Stripe (ensure key is loaded correctly)
# Ensure this is done safely, preferably via app config from env vars
# stripe.api_key = os.getenv('STRIPE_SECRET_KEY') # Loaded in app.py usually

# Create upload folder if it doesn't exist
# This might be better done at app startup or using Flask commands
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
except OSError as e:
    # Log this error if it happens during import time
    print(f"Error creating upload folder {UPLOAD_FOLDER}: {e}")


challenge_manager = ChallengeManager() # Instantiate manager
# csrf = CSRFProtect() # Initialize if enabling CSRF and initializing it here

# --- Helper Functions ---

def validate_image(stream):
    """Validate file is actually an image using python-magic"""
    try:
        mime = magic.Magic(mime=True)
        buffer = stream.read(2048)
        stream.seek(0) # Reset stream position crucial
        if not buffer: return None
        mime_type = mime.from_buffer(buffer)
        if not mime_type.startswith('image/'): return None
        mime_to_ext = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif', 'image/webp': '.webp'}
        return mime_to_ext.get(mime_type)
    except Exception as e:
        # Use logger if app context is available, otherwise print
        logger = current_app.logger if current_app else print
        logger(f"Error validating image: {e}", exc_info=True)
        return None

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_file(file):
    """Save file with security checks"""
    if not file or not file.filename: return None
    if not allowed_file(file.filename):
        flash(f"File extension not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}", "warning")
        return None

    img_ext = validate_image(file.stream) # Use file.stream
    if not img_ext:
         flash(f"File content does not appear to be a valid image.", "warning")
         return None

    try:
        filename = secure_filename(str(uuid4()) + img_ext)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        return filename
    except Exception as e:
        logger = current_app.logger if current_app else print
        logger(f"Error saving file {file.filename}: {e}", exc_info=True)
        flash("An error occurred while saving the uploaded file.", "error")
        return None

# --- Decorators ---

def buyer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('user_login'))

        buyer = db_session.query(Buyer).filter_by(user_id=current_user.username).first()
        required_challenges = 3 # Configurable?

        if not buyer:
            flash('Create a buyer profile and complete challenges to access the marketplace.', 'info')
            return redirect(url_for('marketplace.buyer_verification'))

        # Use actual verification logic (e.g., check solved challenges count)
        # Assuming Buyer model has 'solved_challenges' list/JSON field
        solved_count = len(buyer.get_solved_challenges())
        if solved_count < required_challenges:
             flash(f'You need to complete at least {required_challenges} easy challenges to access this page.', 'warning')
             return redirect(url_for('marketplace.buyer_verification'))

        # Add check for email verification IF it was still a requirement
        # if not current_user.email_verified:
        #     flash('Please verify your email address.', 'warning')
        #     return redirect(url_for('profile.index')) # Or wherever verification request is handled

        return f(*args, **kwargs)
    return decorated_function

def seller_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in first.', 'warning')
            return redirect(url_for('auth.login'))  # or whatever your login route is

        seller = db_session.query(Seller).filter_by(user_id=current_user.username).first()
        
        if not seller:
            flash('Seller profile not found. Please register as a seller first.', 'danger')
            return redirect(url_for('marketplace.become_seller'))  # redirect to safe route

        if len(seller.get_solved_challenges()) < 5:
            flash(f'You need {5 - len(seller.get_solved_challenges())} more hard challenges to sell.', 'warning')
            return redirect(url_for('marketplace.seller_verification'))

        return f(*args, **kwargs)  # Don't pass seller, routes do their own lookup
    return decorated_function


# --- NOW Define Routes using the Blueprint ---

@marketplace_bp.route('/')
def index():
    """Marketplace landing page - shows products if buyer is verified."""
    products = []
    buyer = None
    seller = None
    if current_user.is_authenticated:
        buyer = db_session.query(Buyer).filter_by(user_id=current_user.username).first()
        seller = db_session.query(Seller).filter_by(user_id=current_user.username).first()
        required_challenges = 3
        solved_count = len(buyer.get_solved_challenges()) if buyer else 0
        # Check verification status (challenges completed, potentially other checks later)
        if buyer and solved_count >= required_challenges:
            products = db_session.query(Product).filter_by(is_active=True).order_by(Product.created_at.desc()).all()
            return render_template('marketplace/index.html', products=products, buyer=buyer, seller=seller)

    return render_template('marketplace/welcome.html', buyer=buyer, seller=seller)


@marketplace_bp.route('/buyer/verify')
@login_required
def buyer_verification():
    """Page for buyers to see challenge status for verification."""
    buyer = db_session.query(Buyer).filter_by(user_id=current_user.username).first()
    required_count = 3

    if buyer and len(buyer.get_solved_challenges()) >= required_count:
        flash('You are already a verified buyer!', 'success')
        return redirect(url_for('marketplace.view_products'))

    try:
        all_challenges = challenge_manager.get_all_challenges()
        easy_challenges = {k: v for k, v in all_challenges.items() if v.get('difficulty') == 'easy'}
    except Exception as e:
        current_app.logger.error(f"Failed to get challenges for buyer verification: {e}", exc_info=True)
        flash("Could not load challenges. Please try again later.", "error")
        easy_challenges = {}

    solved_challenge_ids = set(buyer.get_solved_challenges() if buyer else [])
    solved_easy_count = sum(1 for c_id in easy_challenges if c_id in solved_challenge_ids)

    return render_template('marketplace/buyer_verification.html',
                           easy_challenges=easy_challenges,
                           solved_challenge_ids=solved_challenge_ids,
                           solved_easy_count=solved_easy_count,
                           required_count=required_count,
                           buyer=buyer)


@marketplace_bp.route('/products')
@login_required
@buyer_required # Handles verification checks
def view_products():
    """View all products (requires buyer verification)"""
    products = db_session.query(Product).filter_by(is_active=True).order_by(Product.created_at.desc()).all()
    return render_template('marketplace/products.html', products=products)


@marketplace_bp.route("/seller/register", methods=["GET", "POST"])
def seller_register():
    """Register a NEW user AS a seller (creates User and Seller)."""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        email = request.form.get("email")
        business_name = request.form.get("business_name")
        description = request.form.get("description")

        if not all([username, password, email, business_name]):
            flash("Username, password, email, and business name are required.", "error")
            return render_template("marketplace/seller_register.html")

        if db_session.query(User).filter_by(username=username).first():
            flash("Username already exists", "error")
            return render_template("marketplace/seller_register.html")
        if db_session.query(User).filter_by(email=email).first():
            flash("Email already registered", "error")
            return render_template("marketplace/seller_register.html")

        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            email=email,
            email_verified=True, # Assume verified since we removed the process
            is_active=True,
            is_admin=False
            # created_at=datetime.utcnow() # If applicable
        )
        db_session.add(user)
        try:
             db_session.flush()
        except Exception as e:
             db_session.rollback()
             current_app.logger.error(f"Seller registration flush error for user '{username}': {e}", exc_info=True)
             flash("Registration failed during user creation. Please try again.", "error")
             return render_template("marketplace/seller_register.html")

        seller = Seller(
            user_id=user.username, # Link to user's username (ForeignKey)
            business_name=business_name,
            description=description,
            is_verified=0 # Needs challenge verification
        )
        db_session.add(seller)

        try:
            db_session.commit()
            login_user(user)
            # Removed email sending
            flash("Registration successful!", "success")
            return redirect(url_for("marketplace.seller_verification"))
        except Exception as e:
            db_session.rollback()
            print(f"Seller Registration failed for user '{username}'. Error: {e}")
            print(traceback.format_exc())
            current_app.logger.error(f"Seller Registration failed for user '{username}': {e}", exc_info=True)
            flash("Registration failed. Please try again.", "error")
            return render_template("marketplace/seller_register.html")

    return render_template("marketplace/seller_register.html")


@marketplace_bp.route("/buyer/register", methods=["GET", "POST"])
def buyer_register():
    """Register a NEW user AS a buyer (creates User and Buyer)."""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        email = request.form.get("email")
        display_name = request.form.get("display_name")

        if not all([username, password, email, display_name]):
             flash("Username, password, email, and display name are required.", "error")
             return render_template("marketplace/buyer_register.html")

        if db_session.query(User).filter_by(username=username).first():
            flash("Username already exists", "error")
            return render_template("marketplace/buyer_register.html")
        if db_session.query(User).filter_by(email=email).first():
            flash("Email already registered", "error")
            return render_template("marketplace/buyer_register.html")

        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            email=email,
            email_verified=True, # Assume verified
            is_active=True,
            is_admin=False
            # created_at=datetime.utcnow() # If applicable
        )
        db_session.add(user)
        try:
             db_session.flush()
        except Exception as e:
             db_session.rollback()
             current_app.logger.error(f"Buyer registration flush error for user '{username}': {e}", exc_info=True)
             flash("Registration failed during user creation. Please try again.", "error")
             return render_template("marketplace/buyer_register.html")

        buyer = Buyer(
            user_id=user.username, # Link to user's username (ForeignKey)
            display_name=display_name,
            is_verified=0 # Needs challenge verification
        )
        db_session.add(buyer)

        try:
            db_session.commit()
            login_user(user)
            # Removed email sending
            flash("Registration successful!", "success")
            return redirect(url_for("marketplace.buyer_verification"))
        except Exception as e:
            db_session.rollback()
            print(f"Buyer Registration failed for user '{username}'. Error: {e}")
            print(traceback.format_exc())
            current_app.logger.error(f"Buyer Registration failed for user '{username}': {e}", exc_info=True)
            flash("Registration failed. Please try again.", "error")
            return render_template("marketplace/buyer_register.html")

    return render_template("marketplace/buyer_register.html")


# --- This route seems redundant? ---
# Renaming endpoint slightly to avoid clash if needed
# Use this if a LOGGED IN user wants to ADD a seller profile
@marketplace_bp.route('/become-seller', methods=['GET', 'POST'])
@login_required
def become_seller():
    """Allow logged-in user to register as a seller (creates Seller profile only)."""
    if db_session.query(Seller).filter_by(user_id=current_user.username).first():
        flash('You are already registered as a seller.', 'info')
        return redirect(url_for('marketplace.seller_verification'))

    if request.method == 'POST':
        business_name = request.form.get('business_name')
        description = request.form.get('description')

        if not business_name:
            flash('Business name is required.', 'error')
            # Re-render the same form on error
            return render_template('marketplace/become_seller_form.html')

        seller = Seller(
            user_id=current_user.username,
            business_name=business_name,
            description=description,
            is_verified=0
        )
        try:
            db_session.add(seller)
            db_session.commit()
            flash('Successfully registered as a seller. Complete 5 hard challenges to start selling!', 'success')
            return redirect(url_for('marketplace.seller_verification'))
        except Exception as e:
            db_session.rollback()
            current_app.logger.error(f"Error registering existing user {current_user.id} as seller: {e}", exc_info=True)
            flash("Failed to register as seller. Please try again.", "error")

    # Show form for existing user to add seller details
    return render_template('marketplace/become_seller_form.html') # Needs this template


@marketplace_bp.route('/seller/verification')
@login_required
def seller_verification():
    """Page for sellers to see challenge status for verification."""
    seller = db_session.query(Seller).filter_by(user_id=current_user.username).first()
    required_count = 5

    if seller and len(seller.get_solved_challenges()) >= required_count:
        flash('You are already a verified seller!', 'success')
        return redirect(url_for('marketplace.seller_products'))

    try:
        all_challenges = challenge_manager.get_all_challenges()
        hard_challenges = {k: v for k, v in all_challenges.items() if v.get('difficulty') == 'hard'}
    except Exception as e:
        current_app.logger.error(f"Failed to get challenges for seller verification: {e}", exc_info=True)
        flash("Could not load challenges. Please try again later.", "error")
        hard_challenges = {}

    solved_challenge_ids = set(seller.get_solved_challenges() if seller else [])
    solved_hard_count = sum(1 for c_id in hard_challenges if c_id in solved_challenge_ids)

    return render_template('marketplace/seller_verification.html',
                           hard_challenges=hard_challenges,
                           solved_challenge_ids=solved_challenge_ids,
                           solved_hard_count=solved_hard_count,
                           required_count=required_count,
                           seller=seller)


@marketplace_bp.route('/products/new', methods=['GET', 'POST'])
@login_required
@seller_required
def create_product():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description', '')
        price = float(request.form.get('price', 0))
        stock = int(request.form.get('stock', 0))
        category = request.form.get('category') or 'Other'

        # Image upload
        image_filename = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                image_filename = save_file(file)

        # ←←← THIS WAS THE BUG ←←←
        seller = db_session.query(Seller).filter_by(user_id=current_user.username).first()

        if not seller:
            flash('Seller profile not found. Please contact admin.', 'error')
            return redirect(url_for('marketplace.index'))

        product = Product(
            seller_id=seller.id,           # now safe because seller exists
            name=name,
            description=description,
            price=price,
            stock=stock,
            category=category,
            image_path=image_filename,
            is_active=True
        )
        db_session.add(product)
        db_session.commit()

        flash('Product created successfully!', 'success')
        return redirect(url_for('marketplace.seller_products'))

    return render_template('marketplace/create_product.html')

@marketplace_bp.route('/products/manage')
@login_required
@seller_required
def seller_products():
    """List all products for the current seller"""
    seller = db_session.query(Seller).filter_by(user_id=current_user.username).first()
    products = db_session.query(Product).filter_by(seller_id=seller.id).order_by(Product.created_at.desc()).all()
    return render_template('marketplace/seller_products.html', products=products)


@marketplace_bp.route('/products/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
@seller_required
def edit_product(product_id):
    """Edit a product listing"""
    seller = db_session.query(Seller).filter_by(user_id=current_user.username).first()
    product = db_session.query(Product).filter_by(id=product_id, seller_id=seller.id).first()
    if not product: abort(404, description="Product not found or permission denied.")

    if request.method == 'POST':
        name = request.form.get('name')
        price_str = request.form.get('price')
        stock_str = request.form.get('stock')
        if not name or not price_str or not stock_str:
             flash('Name, price, and stock are required.', 'error')
             return render_template('marketplace/edit_product.html', product=product)
        try:
            price = float(price_str); stock = int(stock_str)
            if price <= 0 or stock < 0: raise ValueError("Invalid price/stock.")
        except ValueError:
             flash('Invalid price or stock value.', 'error')
             return render_template('marketplace/edit_product.html', product=product)

        product.name = name
        product.description = request.form.get('description')
        product.price = price
        product.stock = stock
        product.category = request.form.get('category')
        product.is_active = request.form.get('is_active') == 'on'

        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                image_filename = save_file(file)
                if not image_filename: return render_template('marketplace/edit_product.html', product=product)
                # Delete old image
                if product.image_filename:
                    try:
                        old_image_path = os.path.join(UPLOAD_FOLDER, product.image_filename)
                        if os.path.exists(old_image_path): os.remove(old_image_path)
                    except OSError as rm_error: logger.warning(f"Could not remove old image {product.image_filename}: {rm_error}")
                product.image_filename = image_filename

        try:
            db_session.commit()
            flash('Product updated successfully!', 'success')
            return redirect(url_for('marketplace.seller_products'))
        except Exception as e:
            db_session.rollback()
            current_app.logger.error(f"Error editing product {product_id}: {e}", exc_info=True)
            flash("Failed to update product. Please try again.", "error")

    return render_template('marketplace/edit_product.html', product=product)


@marketplace_bp.route('/products/<int:product_id>/delete', methods=['POST'])
@login_required
@seller_required
def delete_product(product_id):
    """Delete a product listing"""
    seller = db_session.query(Seller).filter_by(user_id=current_user.username).first()
    product = db_session.query(Product).filter_by(id=product_id, seller_id=seller.id).first()
    if not product:
         flash('Product not found or you do not have permission.', 'error')
         return redirect(url_for('marketplace.seller_products'))

    image_to_delete = product.image_filename
    try:
        db_session.delete(product)
        db_session.commit()
        flash('Product deleted successfully!', 'success')
        # Try removing image file
        if image_to_delete:
            try:
                image_path = os.path.join(UPLOAD_FOLDER, image_to_delete)
                if os.path.exists(image_path): os.remove(image_path)
            except OSError as rm_error: current_app.logger.warning(f"Could not remove image file {image_to_delete}: {rm_error}")
    except Exception as e:
        db_session.rollback()
        current_app.logger.error(f"Error deleting product {product_id}: {e}", exc_info=True)
        flash('Failed to delete product. Please try again.', 'error')

    return redirect(url_for('marketplace.seller_products'))


@marketplace_bp.route('/uploads/products/<path:filename>')
def product_image(filename):
    """Serve product images"""
    if '..' in filename or filename.startswith('/'): abort(400)
    try:
        # Ensure UPLOAD_FOLDER is absolute for send_from_directory
        safe_upload_folder = os.path.abspath(UPLOAD_FOLDER)
        return send_from_directory(safe_upload_folder, filename)
    except FileNotFoundError:
         abort(404)


# --- M-Pesa Payment Routes ---

@marketplace_bp.route('/checkout/<int:product_id>', methods=['GET', 'POST'])
@login_required
@buyer_required
def checkout(product_id):
    """Handle product checkout with M-Pesa, Stripe, or Crypto"""
    buyer = db_session.query(Buyer).filter_by(user_id=current_user.username).first()
    product = db_session.query(Product).get(product_id)

    if not product or not product.is_active:
        flash("Product not found or is no longer available.", "error")
        return redirect(url_for('marketplace.view_products'))
    if product.stock <= 0:
        flash("Sorry, this product is out of stock.", "warning")
        return redirect(url_for('marketplace.view_products'))

    if request.method == 'GET':
        return render_template('marketplace/checkout.html', product=product)
    
    # POST - Process payment
    payment_method_id = request.form.get('payment_method_id')
    phone_number = request.form.get('phone_number', '')
    delivery_address = request.form.get('delivery_address', '')
    
    if not payment_method_id:
        flash("Please select a payment method.", "error")
        return render_template('marketplace/checkout.html', product=product)

    # Handle M-Pesa payment
    if payment_method_id == 'mpesa':
        if not phone_number or len(phone_number) < 9:
            flash("Please enter a valid Safaricom phone number.", "error")
            return render_template('marketplace/checkout.html', product=product)
        
        # Format phone number (add 254 prefix if needed)
        formatted_phone = mpesa_client.format_phone_number(phone_number)
        
        # Create pending payment record
        payment = Payment(
            buyer_id=buyer.id,
            product_id=product.id,
            amount=product.price,
            status=PaymentStatus.PENDING,
            payment_method=PaymentMethod.MPESA
        )
        db_session.add(payment)
        db_session.flush()
        
        # Create order with pending status
        order = Order(
            buyer_id=buyer.id,
            product_id=product.id,
            payment_id=payment.id,
            quantity=1,
            total_amount=product.price,
            delivery_status=DeliveryStatus.PENDING,
            delivery_address=delivery_address,
            phone_number=formatted_phone
        )
        db_session.add(order)
        db_session.commit()
        
        # Initiate STK Push
        result = mpesa_client.stk_push(
            phone_number=formatted_phone,
            amount=int(product.price),
            account_reference=f"ORD{order.id}",
            transaction_desc=product.name[:13]
        )
        
        if result.get('success'):
            # Store checkout request ID for callback matching
            payment.checkout_request_id = result.get('checkout_request_id')
            db_session.commit()
            
            flash("Check your phone for M-Pesa PIN prompt!", "success")
            return redirect(url_for('marketplace.mpesa_pending', order_id=order.id))
        else:
            # Rollback on failure
            db_session.delete(order)
            db_session.delete(payment)
            db_session.commit()
            flash(f"M-Pesa Error: {result.get('message')}", "error")
            return render_template('marketplace/checkout.html', product=product)
    
    # Handle Stripe/Crypto (placeholder)
    else:
        try:
            success, message = process_payment(buyer, product, payment_method_id)
            
            if success:
                product.stock -= 1
                db_session.commit()
                
                payment = db_session.query(Payment).filter_by(
                    buyer_id=buyer.id,
                    product_id=product.id
                ).order_by(Payment.created_at.desc()).first()
                
                flash("Purchase successful!", "success")
                return redirect(url_for('marketplace.order_confirmation', payment_id=payment.id if payment else 0))
            else:
                flash(f"Purchase failed: {message}", "error")
                return render_template('marketplace/checkout.html', product=product)
        except Exception as e:
            current_app.logger.error(f"Payment processing error: {e}", exc_info=True)
            flash(f"Payment error: {str(e)}", "error")
            return render_template('marketplace/checkout.html', product=product)


@marketplace_bp.route('/mpesa/pending/<int:order_id>')
@login_required
def mpesa_pending(order_id):
    """Show M-Pesa payment pending page"""
    buyer = db_session.query(Buyer).filter_by(user_id=current_user.username).first()
    order = db_session.query(Order).filter_by(id=order_id, buyer_id=buyer.id).first()
    
    if not order:
        flash("Order not found.", "error")
        return redirect(url_for('marketplace.view_products'))
    
    return render_template('marketplace/mpesa_pending.html', order=order)


@marketplace_bp.route('/mpesa/callback', methods=['POST'])
def mpesa_callback():
    """Handle M-Pesa STK Push callback (webhook)"""
    try:
        callback_data = request.get_json()
        current_app.logger.info(f"M-Pesa Callback received: {callback_data}")
        
        result = mpesa_client.parse_callback(callback_data)
        
        if not result:
            return jsonify({'ResultCode': 1, 'ResultDesc': 'Invalid callback data'}), 400
        
        checkout_request_id = result.get('checkout_request_id')
        
        # Find the payment by checkout request ID
        payment = db_session.query(Payment).filter_by(
            checkout_request_id=checkout_request_id
        ).first()
        
        if not payment:
            current_app.logger.warning(f"Payment not found for checkout_request_id: {checkout_request_id}")
            return jsonify({'ResultCode': 0, 'ResultDesc': 'Accepted'})
        
        if result.get('success'):
            # Update payment status
            payment.status = PaymentStatus.COMPLETED
            payment.transaction_id = result.get('mpesa_receipt')
            payment.completed_at = datetime.utcnow()
            
            # Update order
            order = db_session.query(Order).filter_by(payment_id=payment.id).first()
            if order:
                order.mpesa_receipt_number = result.get('mpesa_receipt')
                order.delivery_status = DeliveryStatus.PROCESSING
                
                # Decrease product stock
                product = db_session.query(Product).get(payment.product_id)
                if product and product.stock > 0:
                    product.stock -= 1
            
            db_session.commit()
            current_app.logger.info(f"M-Pesa payment completed: {result.get('mpesa_receipt')}")
        else:
            # Payment failed
            payment.status = PaymentStatus.FAILED
            db_session.commit()
            current_app.logger.warning(f"M-Pesa payment failed: {result.get('result_desc')}")
        
        return jsonify({'ResultCode': 0, 'ResultDesc': 'Accepted'})
        
    except Exception as e:
        current_app.logger.error(f"M-Pesa callback error: {e}", exc_info=True)
        return jsonify({'ResultCode': 1, 'ResultDesc': str(e)}), 500


@marketplace_bp.route('/mpesa/check/<int:order_id>')
@login_required
def mpesa_check_status(order_id):
    """Check M-Pesa payment status (AJAX endpoint)"""
    buyer = db_session.query(Buyer).filter_by(user_id=current_user.username).first()
    order = db_session.query(Order).filter_by(id=order_id, buyer_id=buyer.id).first()
    
    if not order or not order.payment:
        return jsonify({'status': 'error', 'message': 'Order not found'})
    
    payment = order.payment
    
    if payment.status == PaymentStatus.COMPLETED:
        return jsonify({
            'status': 'completed',
            'receipt': payment.transaction_id,
            'redirect': url_for('marketplace.order_detail', order_id=order.id)
        })
    elif payment.status == PaymentStatus.FAILED:
        return jsonify({'status': 'failed', 'message': 'Payment failed or cancelled'})
    else:
        # Query M-Pesa for status
        if payment.checkout_request_id:
            result = mpesa_client.query_transaction(payment.checkout_request_id)
            return jsonify({
                'status': result.get('status', 'pending'),
                'message': result.get('message', 'Waiting for payment...')
            })
        return jsonify({'status': 'pending', 'message': 'Waiting for payment...'})


# --- Order Management Routes ---

@marketplace_bp.route('/orders')
@login_required
@buyer_required
def my_orders():
    """View buyer's order history"""
    buyer = db_session.query(Buyer).filter_by(user_id=current_user.username).first()
    orders = db_session.query(Order).filter_by(buyer_id=buyer.id).order_by(Order.created_at.desc()).all()
    return render_template('marketplace/orders.html', orders=orders)


@marketplace_bp.route('/orders/<int:order_id>')
@login_required
def order_detail(order_id):
    """View single order details"""
    buyer = db_session.query(Buyer).filter_by(user_id=current_user.username).first()
    order = db_session.query(Order).filter_by(id=order_id, buyer_id=buyer.id).first()
    
    if not order:
        flash("Order not found.", "error")
        return redirect(url_for('marketplace.my_orders'))
    
    return render_template('marketplace/order_detail.html', order=order)


@marketplace_bp.route('/seller/orders')
@login_required
@seller_required
def seller_orders():
    """View seller's orders to fulfill"""
    seller = db_session.query(Seller).filter_by(user_id=current_user.username).first()
    
    # Get all orders for seller's products
    orders = db_session.query(Order).join(Product).filter(
        Product.seller_id == seller.id
    ).order_by(Order.created_at.desc()).all()
    
    return render_template('marketplace/seller_orders.html', orders=orders)


@marketplace_bp.route('/seller/orders/<int:order_id>/update', methods=['POST'])
@login_required
@seller_required
def update_order_status(order_id):
    """Update order delivery status"""
    seller = db_session.query(Seller).filter_by(user_id=current_user.username).first()
    
    # Verify seller owns this order's product
    order = db_session.query(Order).join(Product).filter(
        Order.id == order_id,
        Product.seller_id == seller.id
    ).first()
    
    if not order:
        flash("Order not found or permission denied.", "error")
        return redirect(url_for('marketplace.seller_orders'))
    
    new_status = request.form.get('status')
    try:
        order.delivery_status = DeliveryStatus(new_status)
        if new_status == 'delivered':
            order.delivered_at = datetime.utcnow()
        db_session.commit()
        flash(f"Order status updated to {new_status}.", "success")
    except ValueError:
        flash("Invalid status.", "error")
    
    return redirect(url_for('marketplace.seller_orders'))


@marketplace_bp.route('/payment/<int:payment_id>/confirmation')
@login_required
def order_confirmation(payment_id):
    """Show order confirmation page"""
    buyer = db_session.query(Buyer).filter_by(user_id=current_user.username).first()
    payment = db_session.query(Payment).filter_by(id=payment_id, buyer_id=buyer.id).first()
    
    if not payment:
        flash("Order not found.", "error")
        return redirect(url_for('marketplace.view_products'))
    
    order = db_session.query(Order).filter_by(payment_id=payment.id).first()
    return render_template('marketplace/confirmation.html', payment=payment, order=order)


# --- Routes for Managing Payment Methods (Placeholders) ---

@marketplace_bp.route('/payment-methods', methods=['GET'])
@login_required
@buyer_required
def payment_methods():
    """View and manage payment methods - Placeholder"""
    payment_methods_list = [] # TODO: Fetch from Stripe via helper
    return render_template('marketplace/payment_methods.html', payment_methods=payment_methods_list, stripe_public_key=os.getenv('STRIPE_PUBLIC_KEY'))


@marketplace_bp.route('/payment-methods/add', methods=['POST'])
@login_required
@buyer_required
def add_payment_method():
    """Add a new payment method - Placeholder"""
    stripe_payment_method_id = request.form.get('stripe_payment_method_id')
    if not stripe_payment_method_id:
         flash("Failed to get payment method details from Stripe.", "error")
         return redirect(url_for('marketplace.payment_methods'))
    buyer = db_session.query(Buyer).filter_by(user_id=current_user.username).first()
    try:
        # TODO: Implement Stripe customer creation/attachment logic
        flash("Payment method added successfully (Placeholder).", "success")
    except Exception as e:
        current_app.logger.error(f"Error adding payment method for user {current_user.id}: {e}", exc_info=True)
        flash(f"Error adding payment method: {str(e)}", "error")
    return redirect(url_for('marketplace.payment_methods'))


@marketplace_bp.route('/payment-methods/delete', methods=['POST'])
@login_required
@buyer_required
def delete_payment_method():
    """Delete a payment method - Placeholder"""
    stripe_payment_method_id = request.form.get('stripe_payment_method_id')
    if not stripe_payment_method_id:
        flash("No payment method specified for deletion.", "error")
        return redirect(url_for('marketplace.payment_methods'))
    try:
        # TODO: Implement Stripe detach logic
        success = True # Placeholder
        if success: flash("Payment method detached successfully (Placeholder).", "success")
        else: flash("Failed to detach payment method via Stripe (Placeholder).", "error")
    except Exception as e:
        current_app.logger.error(f"Error deleting payment method {stripe_payment_method_id} for user {current_user.id}: {e}", exc_info=True)
        flash(f"Error deleting payment method: {str(e)}", "error")
    return redirect(url_for('marketplace.payment_methods'))


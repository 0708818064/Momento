import stripe
from flask import current_app
from core.marketplace.models import Payment, PaymentStatus, PaymentMethod
from core.database import db_session
from datetime import datetime

def init_stripe(app):
    stripe.api_key = app.config['STRIPE_SECRET_KEY']

def create_payment_intent(amount, currency='usd'):
    """Create a Stripe PaymentIntent"""
    try:
        intent = stripe.PaymentIntent.create(
            amount=int(amount * 100),  # Convert to cents
            currency=currency,
            automatic_payment_methods={'enabled': True}
        )
        return intent
    except stripe.error.StripeError as e:
        raise Exception(f"Stripe error: {str(e)}")

def create_payment_method(payment_details):
    """Create a Stripe PaymentMethod"""
    try:
        payment_method = stripe.PaymentMethod.create(
            type="card",
            card={
                "number": payment_details["card_number"],
                "exp_month": payment_details["exp_month"],
                "exp_year": payment_details["exp_year"],
                "cvc": payment_details["cvc"],
            },
        )
        return payment_method
    except stripe.error.StripeError as e:
        raise Exception(f"Stripe error: {str(e)}")

def process_payment(buyer, product, payment_method_id):
    """Process a payment for a product"""
    import os
    import uuid
    
    # Check if we're in demo mode (placeholder Stripe keys)
    stripe_key = os.getenv('STRIPE_SECRET_KEY', '')
    is_demo_mode = not stripe_key or 'your_stripe' in stripe_key or stripe_key.startswith('sk_test_your')
    
    payment = None
    try:
        # Create payment record
        payment = Payment(
            buyer_id=buyer.id,
            product_id=product.id,
            amount=product.price,
            payment_method=PaymentMethod.STRIPE,
            status=PaymentStatus.PENDING
        )
        db_session.add(payment)
        
        if is_demo_mode:
            # Demo mode - simulate successful payment
            payment.status = PaymentStatus.COMPLETED
            payment.transaction_id = f"demo_{uuid.uuid4().hex[:16]}"
            payment.completed_at = datetime.utcnow()
            db_session.commit()
            return True, "Payment successful (Demo Mode)"
        
        # Real Stripe payment
        intent = create_payment_intent(product.price)
        
        # Confirm payment
        intent.confirm(payment_method=payment_method_id)
        
        if intent.status == 'succeeded':
            payment.status = PaymentStatus.COMPLETED
            payment.transaction_id = intent.id
            payment.completed_at = datetime.utcnow()
            db_session.commit()
            return True, "Payment successful"
        else:
            payment.status = PaymentStatus.FAILED
            db_session.commit()
            return False, "Payment failed"
            
    except Exception as e:
        if payment:
            payment.status = PaymentStatus.FAILED
            db_session.commit()
        return False, str(e)

def get_payment_methods(buyer):
    """Get saved payment methods for a buyer"""
    try:
        payment_methods = stripe.PaymentMethod.list(
            customer=buyer.stripe_customer_id,
            type="card"
        )
        return payment_methods.data
    except stripe.error.StripeError as e:
        raise Exception(f"Stripe error: {str(e)}")

def delete_payment_method(payment_method_id):
    """Delete a saved payment method"""
    try:
        stripe.PaymentMethod.detach(payment_method_id)
        return True
    except stripe.error.StripeError:
        return False

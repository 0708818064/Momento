"""
M-Pesa Daraja API Integration
Safaricom M-Pesa STK Push (Lipa Na M-Pesa Online)
"""
import os
import base64
import requests
from datetime import datetime
from typing import Optional, Dict, Any, Tuple


class MpesaClient:
    """
    M-Pesa Daraja API Client for STK Push payments.
    
    Usage:
        client = MpesaClient()
        result = client.stk_push(
            phone_number="254712345678",
            amount=100,
            account_reference="Order123",
            transaction_desc="Product Purchase"
        )
    """
    
    SANDBOX_BASE_URL = "https://sandbox.safaricom.co.ke"
    PRODUCTION_BASE_URL = "https://api.safaricom.co.ke"
    
    def __init__(self):
        self.consumer_key = os.getenv('MPESA_CONSUMER_KEY', '')
        self.consumer_secret = os.getenv('MPESA_CONSUMER_SECRET', '')
        self.shortcode = os.getenv('MPESA_SHORTCODE', '174379')  # Sandbox default
        self.passkey = os.getenv('MPESA_PASSKEY', '')
        self.callback_url = os.getenv('MPESA_CALLBACK_URL', '')
        self.env = os.getenv('MPESA_ENV', 'sandbox')
        
        self.base_url = self.PRODUCTION_BASE_URL if self.env == 'production' else self.SANDBOX_BASE_URL
        self._access_token = None
        self._token_expiry = None
    
    def _get_base_url(self) -> str:
        """Get API base URL based on environment."""
        return self.base_url
    
    def get_access_token(self) -> Optional[str]:
        """
        Get OAuth access token from Daraja API.
        Token is cached and reused until expiry.
        """
        # Return cached token if still valid
        if self._access_token and self._token_expiry:
            if datetime.now() < self._token_expiry:
                return self._access_token
        
        try:
            url = f"{self._get_base_url()}/oauth/v1/generate?grant_type=client_credentials"
            
            # Create Basic Auth header
            credentials = f"{self.consumer_key}:{self.consumer_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            
            headers = {
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            self._access_token = data.get('access_token')
            
            # Token typically expires in 3600 seconds, cache for 50 minutes
            from datetime import timedelta
            self._token_expiry = datetime.now() + timedelta(minutes=50)
            
            return self._access_token
            
        except requests.RequestException as e:
            print(f"M-Pesa OAuth Error: {e}")
            return None
    
    def _generate_password(self) -> Tuple[str, str]:
        """
        Generate the password for STK Push.
        Password = Base64(Shortcode + Passkey + Timestamp)
        """
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password_str = f"{self.shortcode}{self.passkey}{timestamp}"
        password = base64.b64encode(password_str.encode()).decode()
        return password, timestamp
    
    def format_phone_number(self, phone: str) -> str:
        """
        Format phone number to 254XXXXXXXXX format.
        Handles: 0712345678, +254712345678, 254712345678, 712345678
        """
        phone = phone.strip().replace(" ", "").replace("-", "")
        
        if phone.startswith("+"):
            phone = phone[1:]
        
        if phone.startswith("0"):
            phone = "254" + phone[1:]
        elif not phone.startswith("254"):
            phone = "254" + phone
        
        return phone
    
    def stk_push(
        self,
        phone_number: str,
        amount: int,
        account_reference: str,
        transaction_desc: str = "Payment"
    ) -> Dict[str, Any]:
        """
        Initiate STK Push (Lipa Na M-Pesa Online).
        
        Args:
            phone_number: Customer phone number (any format)
            amount: Amount in KES (integer)
            account_reference: Your order/reference number
            transaction_desc: Description shown to customer
            
        Returns:
            Dict with success status, checkout_request_id, and message
        """
        access_token = self.get_access_token()
        if not access_token:
            return {
                'success': False,
                'message': 'Failed to get M-Pesa access token'
            }
        
        password, timestamp = self._generate_password()
        phone = self.format_phone_number(phone_number)
        
        url = f"{self._get_base_url()}/mpesa/stkpush/v1/processrequest"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": self.shortcode,
            "PhoneNumber": phone,
            "CallBackURL": self.callback_url,
            "AccountReference": account_reference[:12],  # Max 12 chars
            "TransactionDesc": transaction_desc[:13]  # Max 13 chars
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            data = response.json()
            
            if response.status_code == 200 and data.get('ResponseCode') == '0':
                return {
                    'success': True,
                    'checkout_request_id': data.get('CheckoutRequestID'),
                    'merchant_request_id': data.get('MerchantRequestID'),
                    'message': 'STK Push sent successfully. Check your phone.'
                }
            else:
                return {
                    'success': False,
                    'message': data.get('errorMessage') or data.get('ResponseDescription') or 'STK Push failed'
                }
                
        except requests.RequestException as e:
            return {
                'success': False,
                'message': f'Network error: {str(e)}'
            }
    
    def query_transaction(self, checkout_request_id: str) -> Dict[str, Any]:
        """
        Query the status of an STK Push transaction.
        
        Args:
            checkout_request_id: The CheckoutRequestID from stk_push response
            
        Returns:
            Dict with transaction status
        """
        access_token = self.get_access_token()
        if not access_token:
            return {
                'success': False,
                'message': 'Failed to get access token'
            }
        
        password, timestamp = self._generate_password()
        
        url = f"{self._get_base_url()}/mpesa/stkpushquery/v1/query"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            data = response.json()
            
            result_code = data.get('ResultCode')
            
            if result_code == '0' or result_code == 0:
                return {
                    'success': True,
                    'status': 'completed',
                    'message': 'Transaction completed successfully'
                }
            elif result_code == '1032':
                return {
                    'success': False,
                    'status': 'cancelled',
                    'message': 'Transaction cancelled by user'
                }
            elif result_code == '1037':
                return {
                    'success': False,
                    'status': 'timeout',
                    'message': 'Transaction timed out'
                }
            else:
                return {
                    'success': False,
                    'status': 'pending',
                    'message': data.get('ResponseDescription', 'Transaction pending')
                }
                
        except requests.RequestException as e:
            return {
                'success': False,
                'status': 'error',
                'message': f'Query error: {str(e)}'
            }
    
    @staticmethod
    def parse_callback(callback_data: Dict) -> Dict[str, Any]:
        """
        Parse M-Pesa STK Push callback data.
        
        Args:
            callback_data: The JSON body from M-Pesa callback
            
        Returns:
            Parsed transaction details
        """
        try:
            body = callback_data.get('Body', {})
            stk_callback = body.get('stkCallback', {})
            
            result_code = stk_callback.get('ResultCode')
            result_desc = stk_callback.get('ResultDesc', '')
            merchant_request_id = stk_callback.get('MerchantRequestID', '')
            checkout_request_id = stk_callback.get('CheckoutRequestID', '')
            
            result = {
                'success': result_code == 0,
                'result_code': result_code,
                'result_desc': result_desc,
                'merchant_request_id': merchant_request_id,
                'checkout_request_id': checkout_request_id,
            }
            
            # Parse callback metadata if successful
            if result_code == 0:
                metadata = stk_callback.get('CallbackMetadata', {})
                items = metadata.get('Item', [])
                
                for item in items:
                    name = item.get('Name', '')
                    value = item.get('Value')
                    
                    if name == 'Amount':
                        result['amount'] = value
                    elif name == 'MpesaReceiptNumber':
                        result['mpesa_receipt'] = value
                    elif name == 'TransactionDate':
                        result['transaction_date'] = str(value)
                    elif name == 'PhoneNumber':
                        result['phone_number'] = str(value)
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }


# Singleton instance
mpesa_client = MpesaClient()

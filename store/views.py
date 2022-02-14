from telnetlib import STATUS
from django.shortcuts import render,HttpResponse , redirect
from django.template import context
from store.forms.authforms import CustomerCreationForm , CustomerAuthForm
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate, login as loginUser , logout
from store.models import Tshirt, SizeVariant , Cart , Order , OrderItem , Payment , Occasion , Brand , Color , IdealFor , NeckType , Sleeve 
from math import ceil
from django.contrib.auth.decorators import login_required
from store.forms.checkout_form import CheckForm
from Tshop.settings import API_KEY , AUTH_TOKEN
from instamojo_wrapper import Instamojo
from django.views.generic.base import View
from django.core.paginator import Paginator
from urllib.parse import urlencode
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView

API = Instamojo(api_key=API_KEY,auth_token=AUTH_TOKEN,endpoint='https://test.instamojo.com/api/1.1/')
# Create your views here.

class LoginView(View):  
    def get(self , request):
        form = CustomerAuthForm()
        print('LOGIN VIEW CLASS')
        next_page = request.GET.get('next')
        if next_page is not None:
            request.session['next_page'] = next_page
        return render(request,
                      template_name='store/login.html',
                      context={'form': form})

    def post(self , request):
        form = CustomerAuthForm(data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user:
                loginUser(request, user)

                session_cart = request.session.get('cart')
                if session_cart is None:
                    session_cart = []
                else:
                    for c in session_cart:
                        size = c.get('size')
                        tshirt_id = c.get('tshirt')
                        quantity = c.get('quantity')
                        cart_obj = Cart()
                        cart_obj.sizeVariant = SizeVariant.objects.get(size=size, tshirt=tshirt_id)
                        cart_obj.quantity = quantity
                        cart_obj.user = user
                        cart_obj.save()

                # { size , tshirt , quantity }
                cart = Cart.objects.filter(user=user)
                session_cart = []
                for c in cart:
                    obj = {
                        'size': c.sizeVariant.size,
                        'tshirt': c.sizeVariant.tshirt.id,
                        'quantity': c.quantity
                    }
                    session_cart.append(obj)

                request.session['cart'] = session_cart
                next_page = request.session.get('next_page')
                if next_page is None:
                    next_page = 'homepage'
                return redirect(next_page)
        else:
            return render(request,template_name='store/login.html',context={'form': form})

class OrderListView(ListView):
    template_name = 'store/orders.html'
    model = Order
    paginate_by = 5
    context_object_name = 'orders'

    def get_queryset(self):
        return  Order.objects.filter(user = self.request.user).order_by('-date').exclude(
        order_status='PENDING')

       
class ProductDetailView(DetailView):
    template_name = 'store/product_details.html'
    model = Tshirt
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tshirt = context.get('tshirt') 
        request = self.request
        size = request.GET.get('size')
        if size is None:
            size = tshirt.sizevariant_set.all().order_by('price').first()
        else:
            size = tshirt.sizevariant_set.get(size=size)

        size_price = ceil(size.price)

        sell_price = size_price - (size_price * (tshirt.discount / 100))
        sell_price = ceil(sell_price)

        context = {
            'tshirt': tshirt,
            'price': size_price,
            'sell_price': sell_price,
            'active_size': size
        }
        return context
    

def signup(request):
    if (request.method == 'GET'):
        form = CustomerCreationForm()
        context = {"form": form}
        return render(request,template_name='store/signup.html',context=context)

    else:
        form = CustomerCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.email = user.username
            user.save()
            print(user)
            return redirect('login')
        context = {"form": form}
        return render(request,template_name='store/signup.html',context=context)

def signout(request):
    logout(request)
    return render(request, template_name='store/home.html')

def add_to_cart(request, slug, size):
    user = None
    if request.user.is_authenticated:
        user = request.user
    cart = request.session.get('cart')
    if cart is None:
        cart = []

    tshirt = Tshirt.objects.get(slug=slug)
    add_cart_for_anom_user(cart, size, tshirt)
    if user is not None:
        add_cart_to_database(user, size, tshirt)

    request.session['cart'] = cart
    return_url = request.GET.get('return_url')
    return redirect(return_url)

def add_cart_to_database(user, size, tshirt):
    size = SizeVariant.objects.get(size=size, tshirt=tshirt)
    existing = Cart.objects.filter(user=user, sizeVariant=size)

    if len(existing) > 0:
        obj = existing[0]
        obj.quantity = obj.quantity + 1
        obj.save()

    else:
        c = Cart()
        c.user = user
        c.sizeVariant = size
        c.quantity = 1
        c.save()

def add_cart_for_anom_user(cart, size, tshirt):
    flag = True

    for cart_obj in cart:
        t_id = cart_obj.get('tshirt')
        size_short = cart_obj.get('size')
        if t_id == tshirt.id and size == size_short:
            flag = False
            cart_obj['quantity'] = cart_obj['quantity'] + 1

    if flag:
        cart_obj = {'tshirt': tshirt.id, 'size': size, 'quantity': 1}
        cart.append(cart_obj)

def cart(request):
    cart = request.session.get('cart')
    if cart is None:
        cart = []

    for c in cart:
        tshirt_id = c.get('tshirt')
        tshirt = Tshirt.objects.get(id=tshirt_id)
        c['size'] = SizeVariant.objects.get(tshirt=tshirt_id, size=c['size'])
        c['tshirt'] = tshirt

    print(cart)
    return render(request,template_name='store/cart.html',context={'cart': cart})

# utility
def cal_total_payable_amount(cart):
    total = 0
    for c in cart:
        discount = c.get('tshirt').discount
        price = c.get('size').price
        sale_price = ceil(price - (price * (discount / 100)))
        total_of_single_product = sale_price * c.get('quantity')
        total = total + total_of_single_product

    return total

@login_required(login_url='/login/')
def checkout(request):
    # get Request
    if request.method == 'GET':
        form = CheckForm()
        cart = request.session.get('cart')
        if cart is None:
            cart = []

        for c in cart:
            size_str = c.get('size')
            tshirt_id = c.get('tshirt')
            size_obj = SizeVariant.objects.get(size=size_str, tshirt=tshirt_id)
            c['size'] = size_obj
            c['tshirt'] = size_obj.tshirt

        print(cart)

        return render(request, 'store/checkout.html', {
            "form": form,
            'cart': cart
        })
    else:
        # post request
        form = CheckForm(request.POST)
        user = None
        if request.user.is_authenticated:
            user = request.user
        if form.is_valid():
            # payment
            cart = request.session.get('cart')
            if cart is None:
                cart = []
            for c in cart:
                size_str = c.get('size')
                tshirt_id = c.get('tshirt')
                size_obj = SizeVariant.objects.get(size=size_str,tshirt=tshirt_id)
                c['size'] = size_obj
                c['tshirt'] = size_obj.tshirt
            shipping_address = form.cleaned_data.get('shipping_address')
            phone = form.cleaned_data.get('phone')
            payment_method = form.cleaned_data.get('payment_method')
            total = cal_total_payable_amount(cart)
            print(shipping_address, phone, payment_method, total)

            order = Order()
            order.shipping_address = shipping_address
            order.phone = phone
            order.payment_method = payment_method
            order.total = total
            order.order_status = "PENDING"
            order.user = user
            order.save()

            # saving order items
            for c in cart:
                order_item = OrderItem()
                order_item.order = order
                size = c.get('size')
                tshirt = c.get('tshirt')
                order_item.price = ceil(size.price -(size.price *(tshirt.discount / 100)))
                order_item.quantity = c.get('quantity')
                order_item.size = size
                order_item.tshirt = tshirt
                order_item.save()

            buyer_name = f'{user.first_name} {user.last_name}'
            print(buyer_name)
            # crating payment
            response = API.payment_request_create(
                amount=order.total,
                purpose="Payment For Tshirts",
                send_email=False,
                buyer_name=f'{user.first_name} {user.last_name}',
                email=user.email,
                redirect_url="http://localhost:8000/validate_payment")

            payment_request_id = response['payment_request']['id']
            url = response['payment_request']['longurl']

            payment = Payment()
            payment.order = order
            payment.payment_request_id = payment_request_id
            payment.save()
            return redirect(url)
        else:
            return redirect('/checkout/')


def home(request):
    query = request.GET
    tshirts = []
    tshirts = Tshirt.objects.all()

    brand = query.get('brand')
    neckType = query.get('necktype')
    color = query.get('color')
    idealFor = query.get('idealfor')
    sleeve = query.get('sleeve')
    page = query.get('page')

    if(page is None or page == ''):
        page = 1

    if brand != '' and brand is not None:
        tshirts = tshirts.filter(brand__slug=brand)
    if neckType != '' and neckType is not None:
        tshirts = tshirts.filter(neck_type__slug=neckType)
    if color != '' and color is not None:
        tshirts = tshirts.filter(color__slug=color)
    if sleeve != '' and sleeve is not None:
        tshirts = tshirts.filter(sleeve__slug=sleeve)
    if idealFor != '' and idealFor is not None:
        tshirts = tshirts.filter(ideal_for__slug=idealFor)

    occasions = Occasion.objects.all()
    brands = Brand.objects.all()
    sleeves = Sleeve.objects.all()
    idealFor = IdealFor.objects.all()
    neckTypes = NeckType.objects.all()
    colors = Color.objects.all()

    cart = request.session.get('cart')

    paginator = Paginator(tshirts , 6)
    page_object = paginator.get_page(page)

    query = request.GET.copy()
    query['page'] = ''
    pageurl = urlencode(query)

    context = {
        "page_object": page_object,
        "occasions": occasions,
        "brands": brands,
        'colors': colors,
        'sleeves': sleeves,
        'neckTypes': neckTypes,
        'idealFor': idealFor, 
        'pageurl' : pageurl
    }
    return render(request, template_name='store/home.html', context=context)

def validatePayment(request):
    user = None
    if request.user.is_authenticated:
        user = request.user
    print(user)
    payment_request_id = request.GET.get('payment_request_id')
    payment_id = request.GET.get('payment_id')
    print(payment_request_id, payment_id)
    response = API.payment_request_payment_status(payment_request_id,payment_id)
    status = response.get('payment_request').get('payment').get('status')

    if status != "Failed":
        print('Payment Success')
        try:
            payment = Payment.objects.get(
                payment_request_id=payment_request_id)
            payment.payment_id = payment_id
            payment.payment_status = status
            payment.save()

            order = payment.order
            order.order_status = 'PLACED'
            order.save()

            cart = []
            request.session['cart'] = cart
            Cart.objects.filter(user=user).delete()

            return redirect('orders')
        except:
            return render(request, 'store/payment_failed.html')
    else:
        return render(request, 'store/payment_failed.html')
        # // return error page


import json
import socket
from unittest.mock import patch
import pytest
from ticket_discovery import extract_tickets, discover_tickets, _PinnedHTTPS, fetch_page
from travel_preparation import TravelPreparationInput


def test_generic_products_events_nested_offers_and_unpriced_fallback():
    html = '<script type="application/ld+json">' + json.dumps({'@graph':[
        {'@type':'Product','name':'景区门票','offers':[{'name':'全日票','price':'220','priceCurrency':'CNY','url':'/buy/day'}, {'name':'夜场票','price':'120','priceCurrency':'CNY'}]},
        {'@type':'Event','name':'夜间演出','offers':{'priceCurrency':'USD','price':'20'}},
        {'@type':'Product','name':'起价','offers':{'@type':'AggregateOffer','lowPrice':'9','highPrice':'99'}},
    ]}) + '</script>'
    tickets = extract_tickets(html, 'https://park.example/tickets')
    assert [t['title'] for t in tickets] == ['全日票','夜场票','夜间演出','起价']
    assert tickets[0]['purchase_url'] == 'https://park.example/buy/day'
    assert [t['price'] for t in tickets] == ['220','120','','']
    assert tickets[0]['checked_at']


def test_malformed_unsafe_and_dynamic_pages():
    assert extract_tickets('<script>loadTickets()</script>', 'https://park.example') == []
    assert extract_tickets('<script type>loadTickets()</script>', 'https://park.example') == []
    assert extract_tickets('<script type="application/ld+json">{bad</script>', 'https://park.example') == []
    payload={'@type':'Product','name':'票','offers':{'price':'1','priceCurrency':'CNY','url':'http://127.0.0.1'}}
    assert extract_tickets(json.dumps(payload),'https://park.example') == []
    with patch('ticket_discovery.fetch_page',side_effect=TimeoutError):
        assert discover_tickets('https://park.example')['status']=='link_only'


def test_private_dns_blocked_before_connection_and_tls_uses_validated_address():
    for address in ['127.0.0.1','10.0.0.1','169.254.169.254','::1','fe80::1']:
        with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(address,443))]), patch('socket.create_connection') as connect:
            with pytest.raises(ValueError): _PinnedHTTPS('park.example').connect()
            connect.assert_not_called()
    with pytest.raises(ValueError): fetch_page('https://127.0.0.1/')


def test_ticket_fields_validated_and_optional():
    assert TravelPreparationInput().tickets == []
    with pytest.raises(ValueError):
        TravelPreparationInput(tickets=[{'title':'票','price':'NaN'}])
    with pytest.raises(ValueError):
        TravelPreparationInput(tickets=[{'title':'票','purchase_url':'javascript:alert(1)'}])


def test_ticket_tables_ignore_unrelated_prices_and_ranges():
    html = '<table><tr><th>票种</th><th>价格（元）</th></tr><tr><td>成人票</td><td>￥120</td></tr><tr><td>特惠票</td><td>90起</td></tr></table>'
    tickets = extract_tickets(html, 'https://park.example/tickets')
    assert len(tickets) == 1
    assert tickets[0]['title'] == '成人票'
    assert tickets[0]['price'] == '120'
    assert extract_tickets('<table><tr><th>餐饮</th><th>价格</th></tr><tr><td>套餐</td><td>120</td></tr></table>', 'https://park.example') == []

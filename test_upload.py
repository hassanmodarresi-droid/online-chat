import base64
import http.client

# tiny 1x1 PNG (base64)
png_b64 = (
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAA' 
    'AASUVORK5CYII='
)

data = base64.b64decode(png_b64)

boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
crlf = '\r\n'
body = []
body.append(f'--{boundary}')
body.append('Content-Disposition: form-data; name="file"; filename="test.png"')
body.append('Content-Type: image/png')
body.append('')
body = crlf.join(body).encode('utf-8') + crlf.encode('utf-8') + data + crlf.encode('utf-8')
body += f'--{boundary}--'.encode('utf-8') + crlf.encode('utf-8')

conn = http.client.HTTPConnection('localhost', 3000)
headers = {
    'Content-Type': f'multipart/form-data; boundary={boundary}',
    'Content-Length': str(len(body))
}

try:
    conn.request('POST', '/upload', body, headers)
    res = conn.getresponse()
    print('Status:', res.status)
    data = res.read()
    print('Response:', data.decode('utf-8'))
except Exception as e:
    print('Request error:', e)
finally:
    conn.close()

#!/bin/bash
# End-to-end API test script for PetAvatar

API_URL="https://42kw05zl4d.execute-api.us-west-2.amazonaws.com"
API_KEY="nX92rzyA9PVj3lniXfHb6H1Uzk3fC8oOgTNRnUjHMSw"

echo "=== PetAvatar API End-to-End Test ==="
echo ""

# Step 1: Get presigned URL
echo "Step 1: Getting presigned URL..."
RESPONSE=$(curl -s -X GET "$API_URL/presigned-url" -H "x-api-key: $API_KEY")
echo "$RESPONSE" | python3 -m json.tool

JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo ""
echo "Job ID: $JOB_ID"
echo ""

# Step 2: Create a test JPEG image
echo "Step 2: Creating test image..."
python3 << 'EOF'
# Create a minimal valid JPEG
data = bytes([
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
    0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
    0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
    0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
    0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
    0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
    0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
    0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
    0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
    0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x09, 0x0A, 0x0B, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F,
    0x00, 0xFB, 0xD5, 0xDB, 0x20, 0xA8, 0xF1, 0x7E, 0xCD, 0xBF, 0xFF, 0xD9
])
with open('/tmp/test_pet.jpg', 'wb') as f:
    f.write(data)
print("Created test JPEG: /tmp/test_pet.jpg")
EOF
echo ""

# Step 3: Upload image using presigned URL
echo "Step 3: Uploading image to S3..."
UPLOAD_URL=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['upload_url'])")
KEY=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['upload_fields']['key'])")
AWS_KEY=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['upload_fields']['AWSAccessKeyId'])")
TOKEN=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['upload_fields']['x-amz-security-token'])")
POLICY=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['upload_fields']['policy'])")
SIGNATURE=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['upload_fields']['signature'])")

UPLOAD_RESULT=$(curl -s -w "\n%{http_code}" -X POST "$UPLOAD_URL" \
  -F "key=$KEY" \
  -F "AWSAccessKeyId=$AWS_KEY" \
  -F "x-amz-security-token=$TOKEN" \
  -F "policy=$POLICY" \
  -F "signature=$SIGNATURE" \
  -F "Content-Type=image/jpeg" \
  -F "file=@/tmp/test_pet.jpg")

HTTP_CODE=$(echo "$UPLOAD_RESULT" | tail -1)
echo "Upload HTTP Status: $HTTP_CODE"
if [ "$HTTP_CODE" = "204" ] || [ "$HTTP_CODE" = "200" ]; then
    echo "✓ Upload successful!"
else
    echo "✗ Upload failed"
    echo "$UPLOAD_RESULT"
fi
echo ""

# Step 4: Check job status
echo "Step 4: Checking job status..."
STATUS_RESPONSE=$(curl -s -X GET "$API_URL/status/$JOB_ID" -H "x-api-key: $API_KEY")
echo "$STATUS_RESPONSE" | python3 -m json.tool
echo ""

echo "=== Test Complete ==="
echo "Job ID: $JOB_ID"
echo ""
echo "To check status again:"
echo "  curl -s '$API_URL/status/$JOB_ID' -H 'x-api-key: $API_KEY' | python3 -m json.tool"
echo ""
echo "To get results (when completed):"
echo "  curl -s '$API_URL/results/$JOB_ID' -H 'x-api-key: $API_KEY' | python3 -m json.tool"

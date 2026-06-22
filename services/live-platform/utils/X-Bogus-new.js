
const crypto = require('crypto');


const CONSTANTS = {
    BASE64_CHARS: 'Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=',

    ENCRYPT_KEY_PREFIX: "\u0000\u0001\u000e",

    CANVAS_FINGERPRINT: 10000000,


    XBOGUS_PREFIX: [64, 0, 1, 14],

    RC4_PREFIX: [2, 255],

    RC4_KEY: 255
};


function md5(data) {
    const hash = crypto.createHash('md5');

    if (typeof data === 'string') {
        hash.update(data, 'utf-8');
    } else {
        hash.update(data);
    }

    return hash.digest();
}

function customBase64Encode(str) {
    const chars = CONSTANTS.BASE64_CHARS;
    const bytes = [];

    for (let i = 0; i < str.length; i++) {
        bytes.push(str.charCodeAt(i));
    }

    let result = '';

    for (let i = 0; i < bytes.length; i += 3) {
        const byte1 = bytes[i];
        const byte2 = i + 1 < bytes.length ? bytes[i + 1] : 0;
        const byte3 = i + 2 < bytes.length ? bytes[i + 2] : 0;

        const triplet = (byte1 << 16) | (byte2 << 8) | byte3;

        const index1 = (triplet >>> 18) & 0x3F;
        const index2 = (triplet >>> 12) & 0x3F;
        const index3 = (triplet >>> 6) & 0x3F;
        const index4 = triplet & 0x3F;

        result += chars[index1] + chars[index2];
        result += (i + 1 < bytes.length) ? chars[index3] : '=';
        result += (i + 2 < bytes.length) ? chars[index4] : '=';
    }

    return result;
}


function rc4Encrypt(key, data) {
    const sBox = [];
    for (let i = 0; i < 256; i++) {
        sBox[i] = i;
    }

    let j = 0;
    for (let i = 0; i < 256; i++) {
        j = (j + sBox[i] + key.charCodeAt(i % key.length)) % 256;
        [sBox[i], sBox[j]] = [sBox[j], sBox[i]];
    }

    let i = 0;
    j = 0;
    let result = '';

    for (let k = 0; k < data.length; k++) {
        i = (i + 1) % 256;
        j = (j + sBox[i]) % 256;

        [sBox[i], sBox[j]] = [sBox[j], sBox[i]];

        const keyStreamByte = sBox[(sBox[i] + sBox[j]) % 256];
        const encryptedByte = data.charCodeAt(k) ^ keyStreamByte;
        result += String.fromCharCode(encryptedByte & 255);
    }

    return result;
}

function uint32ToBytes(value) {
    return [
        (value >>> 24) & 255,
        (value >>> 16) & 255,
        (value >>> 8) & 255,
        value & 255
    ];
}

function getLastTwoBytes(md5Hash) {
    return md5Hash.slice(-2);
}

function calculateXorChecksum(bytes) {
    let checksum = bytes[0];

    for (let i = 1; i < bytes.length; i++) {
        checksum ^= bytes[i];
    }

    return checksum;
}


function processUserAgent(userAgent) {

    const encrypted = rc4Encrypt(CONSTANTS.ENCRYPT_KEY_PREFIX, userAgent);

    const base64Encoded = typeof btoa !== 'undefined'
        ? btoa(encrypted)
        : Buffer.from(encrypted, 'binary').toString('base64');

    const hash = md5(base64Encoded);

    return getLastTwoBytes(hash);
}


function generateXBogus(paramsStr = '', dataStr = '',userAgent) {
    const queryIndex = paramsStr.indexOf("?");
    const queryString = queryIndex !== -1 ? paramsStr.substr(queryIndex + 1) : "";
    const paramsMd5 = getLastTwoBytes(md5(md5(queryString)));
    const dataMd5 = getLastTwoBytes(md5(md5(dataStr)));

    const uaMd5 = processUserAgent(userAgent);

    const timestamp = Math.floor(Date.now() / 1000);
    const timestampBytes = uint32ToBytes(timestamp);

    const canvasBytes = uint32ToBytes(CONSTANTS.CANVAS_FINGERPRINT);

    const dataArray = []
        .concat(CONSTANTS.XBOGUS_PREFIX)
        .concat(Array.from(paramsMd5))
        .concat(Array.from(dataMd5))
        .concat(Array.from(uaMd5))
        .concat(timestampBytes)
        .concat(canvasBytes);

    const checksum = calculateXorChecksum(dataArray);
    dataArray.push(checksum);

    const dataString = String.fromCharCode(...dataArray);

    const rc4Key = String.fromCharCode(CONSTANTS.RC4_KEY);
    const encrypted = rc4Encrypt(rc4Key, dataString);

    const withPrefix = String.fromCharCode(...CONSTANTS.RC4_PREFIX) + encrypted;

    return customBase64Encode(withPrefix);
}

params_str = "WebIdLastTime=1752645873&aid=1988&app_language=zh-Hans&app_name=tiktok_web&browser_language=zh-CN&browser_name=Mozilla&browser_online=true&browser_platform=Win32&browser_version=5.0%20%28Windows%20NT%2010.0%3B%20Win64%3B%20x64%29%20AppleWebKit%2F537.36%20%28KHTML%2C%20like%20Gecko%29%20Chrome%2F140.0.0.0%20Safari%2F537.36"
data_str = ''
ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
console.log('X-Bogus:',generateXBogus(params_str,data_str,ua))
console.log('X-Bogus长度:',generateXBogus(params_str,data_str,ua).length)


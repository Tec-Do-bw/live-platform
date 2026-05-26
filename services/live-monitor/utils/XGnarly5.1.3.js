const Crypto = require('crypto');

const CONFIG = {
    totalXHRRequests:1, //XHR 总请求数,指XMLHttpRequest接口发起的全部请求总量
    totalFetchRequests:1,//Fetch 总请求数,指fetch API发起的全部请求总量（现代异步请求方式）
    interceptedFetchRequests:1,//拦截的 Fetch 请求数,被监控工具 / 拦截器捕获的 Fetch 请求数量
    interceptedXHRRequests:0,//拦截的 XHR 请求数,被监控工具 / 拦截器捕获的 XMLHttpRequest 请求数量

    // ChaCha20 初始状态数组 (包含固定常量和动态随机值)
    chaCha20State: [
        2517678443, 2718276124, 3212677781, 2633865432,
        217618912, 2931180889, 1498001188, 2157053261,
        211147047, 185100057, 2903579748, 3732962506,
        4294967295 & Date.now(),
        Math.floor(4294967296 * Math.random()),
        Math.floor(4294967296 * Math.random()),
        Math.floor(4294967296 * Math.random())
    ],

    // 随机数生成器的当前索引位置
    randomKeyIndex: 0,

    // 随机数生成相关参数 [模数, 掩码, 位移位数等]
    randomParams: [4294967296, 4294965248, 53, 0, 2, 11, 8, 7],

    // ChaCha20 魔数常量 (用于初始化状态)
    chaCha20MagicNumbers: [1196819126, 600974999, 3863347763, 1451689750],

    // 随机种子值 (用于数据混淆)
    randomSeed: Math.floor(Math.abs(1e3 * (Date.now() + Math.random() + Math.random()) % 2147483648)),

    // 版本信息
    version: '5.1.3',
    sdkVersion: "1.0.0.328",

    // 自定义Base64编码字符表
    base64Alphabet: 'u09tbS3UvgDEe6r-ZVMXzLpsAohTn7mdINQlW412GqBjfYiyk8JORCF5/xKHwacP=',

    // Canvas指纹图片 (用于生成唯一标识)
    canvasFingerprint: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADAAAAAQCAYAAABQrvyxAAACvklEQVR4AcyUP6hPYRjHD0bUHf0JKaWUDAwsQhaDP4Mkyx2MDMpgshkYLJLNcBUZJDHIRAYZGG4mZUFhMCjMfD7n+p6ec5zL9Lv3/nq+7/f5d973fd73eX/Lm/7vF+YQuFrR3ypLZNjJPh4MC1iGUxmyPmERgfaksJaJ34OsFX6GbxXopBaQJIPq4egWFRibJD4z+SaQ9eQj2Bb1A+6kFmCSATmILVtIoL2Q8NTPs+AT4C24j1foU7UA7FYMBq2jDClMNiehCyiezmH4A7A/oUa/eTMaBcZ/YhsTbspN4hqVM3id/w68D7j+LvjbWAEGA3I60ediQQJu+jLGRuAp3YKvAhfaA+//AzeN2tjf91FOAudcDStuUh7CQziE07jfWoh7mPcGyG3FJBdoDYbY8YW3EXPT9qgb34CtnGO4Cb6DKp6cxT7E6c3Y04/R3WS9hWzW+T0M8+rbcJ7eDbhB5mnCVY8vXGNu3gWu6wTHwV0wBTwlqCePsFz8I3wNjImFvSSwG0yDeWXYQjnVfFDtqhvXvoRyGviPIVCbrw7Aq/bEUP+SdXg8jE/wmLhp5/N7W6++F78TB/nw2LAAA/i7W4g95jO2mYCPFuqJ/X2v55kzbBEfrO0z5/n36PvyvWwhzQMLfDe23EwtIMHKfNdK9UU3cIDhBahif1vYWPtsJfEN8L1A/xXb8SxZ3gTUie/BP4wdtQBPNDBTXRbqQWx5luEdGIqnPFzUnLcM24E3cAMey8Hdibfoe7KNOieKN+kfxmwtAH/j6cpBtatu/AvDFVDFB2qePRz/axRvRfbkfPDm1G/V9RsnvRPn24v1HOQAZf/ZLGB6WAB5PTG558BYD5Q1DE/BpMXCV7KIRVdYXFMLMEhes8IBaAvU7mb8x7G3L+JMDHXxpBaQXRxFsTdvw/5NCnV9J/CdAvqgxZffAAAA////IFUjAAAABklEQVQDAJ4moIsDUCHqAAAAAElFTkSuQmCC"
};


let currentKeyIndex = CONFIG.randomKeyIndex;
const chaCha20StateArray = CONFIG.chaCha20State;


function computeMD5Hash(text) {
    return Crypto.createHash('md5').update(text).digest('hex');
}


function circularLeftShift(value, shiftBits) {
    return (value << shiftBits) | (value >>> (32 - shiftBits));
}


function computeCustomStringHash(inputString) {
    const HASH_SEED = 3735928559;      // 初始哈希种子
    const HASH_MULTIPLIER = 65599;     // 哈希乘数
    const ITERATION_COUNT = 32;        // 迭代次数

    let hashValue = HASH_SEED;

    for (let i = 0; i < ITERATION_COUNT; i++) {
        const charCode = inputString.charCodeAt(hashValue % inputString.length);
        hashValue = (HASH_MULTIPLIER * hashValue + charCode) >>> 0;
    }

    return hashValue;
}


function chaCha20QuarterRound(state, indexA, indexB, indexC, indexD) {

    state[indexA] += state[indexB];
    state[indexD] = circularLeftShift(state[indexD] ^ state[indexA], 16);


    state[indexC] += state[indexD];
    state[indexB] = circularLeftShift(state[indexB] ^ state[indexC], 12);

    state[indexA] += state[indexB];
    state[indexD] = circularLeftShift(state[indexD] ^ state[indexA], 8);

    state[indexC] += state[indexD];
    state[indexB] = circularLeftShift(state[indexB] ^ state[indexC], 7);
}


function chaCha20BlockTransform(initialState, numRounds) {
    const workingState = initialState.slice();


    for (let round = 0; round < numRounds; round++) {
        chaCha20QuarterRound(workingState, 0, 4, 8, 12);
        chaCha20QuarterRound(workingState, 1, 5, 9, 13);
        chaCha20QuarterRound(workingState, 2, 6, 10, 14);
        chaCha20QuarterRound(workingState, 3, 7, 11, 15);

        if (++round >= numRounds) break;

        chaCha20QuarterRound(workingState, 0, 5, 10, 15);
        chaCha20QuarterRound(workingState, 1, 6, 11, 12);
        chaCha20QuarterRound(workingState, 2, 7, 12, 13);
        chaCha20QuarterRound(workingState, 3, 4, 13, 14);
    }

    for (let i = 0; i < 16; i++) {
        workingState[i] += initialState[i];
    }

    return workingState;
}


function incrementChaCha20Counter(state) {
    const UINT32_MAX = 4294967295;
    state[12] = (state[12] + 1) & UINT32_MAX;
}


function chaCha20EncryptInPlace(keyState, rounds, dataBytes) {
    const fullWords = Math.floor(dataBytes.length / 4);
    const remainderBytes = dataBytes.length % 4;
    const totalWords = Math.floor((dataBytes.length + 3) / 4);
    const words = Array(totalWords);

    for (let i = 0; i < fullWords; i++) {
        const byteOffset = 4 * i;
        words[i] = dataBytes[byteOffset] |
                   (dataBytes[byteOffset + 1] << 8) |
                   (dataBytes[byteOffset + 2] << 16) |
                   (dataBytes[byteOffset + 3] << 24);
    }

    if (remainderBytes > 0) {
        words[fullWords] = 0;
        for (let i = 0; i < remainderBytes; i++) {
            words[fullWords] |= dataBytes[4 * fullWords + i] << (8 * i);
        }
    }

    const state = keyState.slice();
    for (let blockStart = 0; blockStart + 16 < words.length; blockStart += 16) {
        const keystream = chaCha20BlockTransform(state, rounds);
        incrementChaCha20Counter(state);

        for (let i = 0; i < 16; i++) {
            words[blockStart + i] ^= keystream[i];
        }
    }

    const lastBlockSize = words.length - Math.floor(words.length / 16) * 16;
    const finalKeystream = chaCha20BlockTransform(state, rounds);
    for (let i = 0; i < lastBlockSize; i++) {
        words[words.length - lastBlockSize + i] ^= finalKeystream[i];
    }

    for (let i = 0; i < fullWords; i++) {
        const byteOffset = 4 * i;
        dataBytes[byteOffset] = words[i] & 255;
        dataBytes[byteOffset + 1] = (words[i] >>> 8) & 255;
        dataBytes[byteOffset + 2] = (words[i] >>> 16) & 255;
        dataBytes[byteOffset + 3] = (words[i] >>> 24) & 255;
    }

    if (remainderBytes > 0) {
        for (let i = 0; i < remainderBytes; i++) {
            dataBytes[4 * fullWords + i] = (words[fullWords] >>> (8 * i)) & 255;
        }
    }
}


function generateChaCha20Random() {
    const ROUNDS = CONFIG.randomParams[6];
    const MASK = CONFIG.randomParams[1];
    const SHIFT_BITS = CONFIG.randomParams[5];
    const INDEX_OFFSET = CONFIG.randomParams[6];
    const MAX_INDEX = CONFIG.randomParams[7];
    const RESET_INDEX = CONFIG.randomParams[3];
    const MULTIPLIER = CONFIG.randomParams[0];
    const BASE = CONFIG.randomParams[4];
    const EXPONENT = CONFIG.randomParams[2];

    const randomBlock = chaCha20BlockTransform(chaCha20StateArray, ROUNDS);
    const lowBits = randomBlock[currentKeyIndex];
    const highBits = (MASK & randomBlock[currentKeyIndex + INDEX_OFFSET]) >>> SHIFT_BITS;

    if (MAX_INDEX === currentKeyIndex) {
        incrementChaCha20Counter(chaCha20StateArray);
        currentKeyIndex = RESET_INDEX;
    } else {
        currentKeyIndex++;
    }

    return (lowBits + MULTIPLIER * highBits) / Math.pow(BASE, EXPONENT);
}


function generateEncryptionKey() {
    const KEY_LENGTH = 12;           // 密钥长度: 12个32位整数 = 48字节
    const UINT32_MAX = 4294967296;   // 2^32

    const keyBytes = [];
    const keyIntegers = [];

    for (let i = 0; i < KEY_LENGTH; i++) {
        const randomValue = Math.floor(UINT32_MAX * generateChaCha20Random());
        keyIntegers.push(randomValue);

        keyBytes.push(
            randomValue & 255,
            (randomValue >>> 8) & 255,
            (randomValue >>> 16) & 255,
            (randomValue >>> 24) & 255
        );
    }

    return { keyIntegers, keyBytes };
}


function computeArrayChecksum(dataArray) {
    let checksumValue = dataArray[0];
    const textEncoder = new TextEncoder();

    for (let i = 1; i < dataArray.length; i++) {
        const element = dataArray[i];

        if (typeof element === 'number') {

            checksumValue ^= element;
        } else if (typeof element === 'string') {

            const utf8Bytes = textEncoder.encode(element);
            let intValue = 0;

            for (let j = 0; j < Math.min(4, utf8Bytes.length); j++) {
                intValue = (intValue << 8) | utf8Bytes[j];
            }

            checksumValue ^= (intValue >>> 0);
        }
    }

    return checksumValue;
}

function shuffleArrayWithSeed(arrayToShuffle, shuffleSeed) {

    const LCG_MULTIPLIER = 1664525;
    const LCG_INCREMENT = 1013904223;
    const LCG_MODULUS = 4294967296;  // 2^32

    let lcgState = shuffleSeed;
    let currentIndex = arrayToShuffle.length - 1;

    while (currentIndex > 0) {

        lcgState = (LCG_MULTIPLIER * lcgState + LCG_INCREMENT) % LCG_MODULUS;
        const randomValue = lcgState / LCG_MODULUS;

        const swapIndex = Math.floor((currentIndex + 1) * randomValue);

        [arrayToShuffle[currentIndex], arrayToShuffle[swapIndex]] =
            [arrayToShuffle[swapIndex], arrayToShuffle[currentIndex]];

        currentIndex--;
    }

    return arrayToShuffle;
}


function prepareDataForEncoding(originalDataArray) {
    const checksumValue = computeArrayChecksum(originalDataArray);

    const dataWithChecksum = originalDataArray.concat(checksumValue);

    let firstElementValue = dataWithChecksum[0];
    for (let i = 1; i < dataWithChecksum.length; i++) {
        firstElementValue ^= dataWithChecksum[i];
    }
    dataWithChecksum[0] = firstElementValue;

    const indexedArray = dataWithChecksum.map((value, index) => [index, value]);

    const SEED_INDEX = 8;
    const shuffleSeed = originalDataArray[SEED_INDEX];

    return shuffleArrayWithSeed(indexedArray, shuffleSeed);
}


function encodeIndexedArrayToBytes(shuffledIndexedArray) {
    const resultBytes = [];
    const textEncoder = new TextEncoder();

    for (const [elementIndex, elementValue] of shuffledIndexedArray) {
        resultBytes.push(elementIndex);

        if (typeof elementValue === 'number') {
            if (elementValue <= 65535) {

                const lengthPrefix = new DataView(new ArrayBuffer(2));
                lengthPrefix.setUint16(0, 2, false);
                resultBytes.push(...new Uint8Array(lengthPrefix.buffer));

                const dataView = new DataView(new ArrayBuffer(2));
                dataView.setUint16(0, elementValue, false);
                resultBytes.push(...new Uint8Array(dataView.buffer));
            } else {

                const lengthPrefix = new DataView(new ArrayBuffer(2));
                lengthPrefix.setUint16(0, 4, false);
                resultBytes.push(...new Uint8Array(lengthPrefix.buffer));

                const dataView = new DataView(new ArrayBuffer(4));
                dataView.setUint32(0, elementValue >>> 0, false);
                resultBytes.push(...new Uint8Array(dataView.buffer));
            }
        } else if (typeof elementValue === 'string') {

            const stringBytes = textEncoder.encode(elementValue);

            const lengthPrefix = new DataView(new ArrayBuffer(2));
            lengthPrefix.setUint16(0, stringBytes.length, false);
            resultBytes.push(...new Uint8Array(lengthPrefix.buffer), ...stringBytes);
        }
    }

    resultBytes.unshift(shuffledIndexedArray.length);

    return resultBytes;
}


function encryptStringData(encryptionKey, encryptionRounds, plainTextData) {
    const dataBytes = [];
    for (let i = 0; i < plainTextData.length; i++) {
        dataBytes.push(plainTextData.charCodeAt(i));
    }

    const fullKeyState = CONFIG.chaCha20MagicNumbers.concat(encryptionKey);

    chaCha20EncryptInPlace(fullKeyState, encryptionRounds, dataBytes);

    return String.fromCharCode(...dataBytes);
}


function calculateKeyInsertionPosition(keyBytes, encryptedBytes) {
    let position = 0;

    for (const byteValue of keyBytes) {
        position = (position + byteValue) % (encryptedBytes.length + 1);
    }

    for (const byteValue of encryptedBytes) {
        position = (position + byteValue) % (encryptedBytes.length + 1);
    }

    return position;
}


function embedKeyIntoEncryptedData(keyBytes, encryptedDataString) {
    const KEY_MARKER = 75;

    const encryptedBytes = [];
    for (let i = 0; i < encryptedDataString.length; i++) {
        encryptedBytes.push(encryptedDataString.charCodeAt(i));
    }

    const insertPosition = calculateKeyInsertionPosition(keyBytes, encryptedBytes);

    const combinedBytes = [KEY_MARKER]
        .concat(encryptedBytes.slice(0, insertPosition))
        .concat(keyBytes)
        .concat(encryptedBytes.slice(insertPosition));

    return String.fromCharCode(...combinedBytes);
}


function encodeWithCustomBase64(inputString) {
    const alphabet = CONFIG.base64Alphabet;
    let encodedResult = '';

    for (let i = 0; i < inputString.length; i += 3) {
        const byte1 = inputString.charCodeAt(i);
        const byte2 = (i + 1 < inputString.length) ? inputString.charCodeAt(i + 1) : 0;
        const byte3 = (i + 2 < inputString.length) ? inputString.charCodeAt(i + 2) : 0;

        const triplet = (byte1 << 16) | (byte2 << 8) | byte3;

        encodedResult += alphabet[(triplet >>> 18) & 0x3F];
        encodedResult += alphabet[(triplet >>> 12) & 0x3F];
        encodedResult += (i + 1 < inputString.length) ? alphabet[(triplet >>> 6) & 0x3F] : '=';
        encodedResult += (i + 2 < inputString.length) ? alphabet[triplet & 0x3F] : '=';
    }

    return encodedResult;
}


function computeSpecialIndexValue(timestamp, randomSeed, shiftValue) {
    const timestampHigh = (timestamp >> 16) & 65535;
    const seedHigh = (randomSeed >> 16) & 65535;

    const timestampLow = timestamp & 65535;
    const seedLow = randomSeed & 65535;

    const xorHigh = timestampHigh ^ seedHigh;
    const xorResult = xorHigh ^ timestampLow ^ seedLow;

    return (shiftValue << 16) | xorResult;
}


function generateXGnarly(urlWithParams, postData, userAgent, operationMode = 14) {
    const queryStartIndex = urlWithParams.indexOf("?");
    const queryString = (queryStartIndex !== -1)
        ? urlWithParams.substr(queryStartIndex + 1)
        : "";

    const canvasFingerprint = computeCustomStringHash(CONFIG.canvasFingerprint);
    const currentTimestampMs = Date.now();
    const currentTimestampSec = Math.floor(currentTimestampMs / 1000);

    const signatureDataArray = [
        0,
        65,
        operationMode,
        computeMD5Hash(queryString),
        computeMD5Hash(postData),
        computeMD5Hash(userAgent),
        currentTimestampSec,
        canvasFingerprint,
        CONFIG.randomSeed,
        CONFIG.version,
        CONFIG.sdkVersion,
        1,
        CONFIG.totalXHRRequests + CONFIG.totalFetchRequests,
        CONFIG.interceptedXHRRequests + CONFIG.interceptedFetchRequests,
        computeSpecialIndexValue(currentTimestampSec, CONFIG.randomSeed, 65)
    ];

    const shuffledIndexedData = prepareDataForEncoding(signatureDataArray);

    const encodedBytes = encodeIndexedArrayToBytes(shuffledIndexedData);
    const encodedString = String.fromCharCode(...encodedBytes);

    const { keyIntegers, keyBytes } = generateEncryptionKey();

    let encryptionRounds = 0;
    for (const keyInt of keyIntegers) {
        encryptionRounds = (encryptionRounds + (keyInt & 15)) & 15;
    }
    encryptionRounds += 5;

    const encryptedData = encryptStringData(keyIntegers, encryptionRounds, encodedString);

    const dataWithEmbeddedKey = embedKeyIntoEncryptedData(keyBytes, encryptedData);

    return encodeWithCustomBase64(dataWithEmbeddedKey);
}


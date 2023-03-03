//
//  Whisper.swift
//  Buzz
//
//  Created by Chidi Williams on 20/02/2023.
//

import Foundation

enum WhisperModel: String, CaseIterable, Codable {
    case tiny, tiny_en, base, base_en,small, small_en,  medium, medium_en, large
    
    var id: String {
        displayName.lowercased()
    }
    
    var displayName: String {
        switch self {
        case .tiny:
            return "Tiny"
        case .tiny_en:
            return "Tiny.en"
        case .base:
            return "Base"
        case .base_en:
            return "Base.en"
        case .small:
            return "Small"
        case .small_en:
            return "Small.en"
        case .medium:
            return "Medium"
        case .medium_en:
            return "Medium.en"
        case .large:
            return "Large"
        }
    }
}

enum WhisperTask: String, CaseIterable, Codable {
    case transcribe, translate
}

enum WhisperLanguage: String, CaseIterable, Codable {
    case en, zh, de, es, ru, ko, fr, ja, pt, tr, pl, ca, nl, ar, sv, it, id, hi, fi, vi, he, uk, el, ms, cs, ro, da, hu, ta, no, th, ur, hr, bg, lt, la, mi, ml, cy, sk, te, fa, lv, bn, sr, az, sl, kn, et, mk, br, eu, `is`, hy, ne, mn, bs, kk, sq, sw, gl, mr, pa, si, km, sn, yo, so, af, oc, ka, be, tg, sd, gu, am, yi, lo, uz, fo, ht, ps, tk, nn, mt, sa, lb, my, bo, tl, mg, `as`, tt, haw, ln, ha, ba, jw, su
    
    var fullName: String {
        switch self {
        case .en: return "English"
        case .zh: return "Chinese"
        case .de: return "German"
        case .es: return "Spanish"
        case .ru: return "Russian"
        case .ko: return "Korean"
        case .fr: return "French"
        case .ja: return "Japanese"
        case .pt: return "Portuguese"
        case .tr: return "Turkish"
        case .pl: return "Polish"
        case .ca: return "Catalan"
        case .nl: return "Dutch"
        case .ar: return "Arabic"
        case .sv: return "Swedish"
        case .it: return "Italian"
        case .id: return "Indonesian"
        case .hi: return "Hindi"
        case .fi: return "Finnish"
        case .vi: return "Vietnamese"
        case .he: return "Hebrew"
        case .uk: return "Ukrainian"
        case .el: return "Greek"
        case .ms: return "Malay"
        case .cs: return "Czech"
        case .ro: return "Romanian"
        case .da: return "Danish"
        case .hu: return "Hungarian"
        case .ta: return "Tamil"
        case .no: return "Norwegian"
        case .th: return "Thai"
        case .ur: return "Urdu"
        case .hr: return "Croatian"
        case .bg: return "Bulgarian"
        case .lt: return "Lithuanian"
        case .la: return "Latin"
        case .mi: return "Maori"
        case .ml: return "Malayalam"
        case .cy: return "Welsh"
        case .sk: return "Slovak"
        case .te: return "Telugu"
        case .fa: return "Persian"
        case .lv: return "Latvian"
        case .bn: return "Bengali"
        case .sr: return "Serbian"
        case .az: return "Azerbaijani"
        case .sl: return "Slovenian"
        case .kn: return "Kannada"
        case .et: return "Estonian"
        case .mk: return "Macedonian"
        case .br: return "Breton"
        case .eu: return "Basque"
        case .is: return "Icelandic"
        case .hy: return "Armenian"
        case .ne: return "Nepali"
        case .mn: return "Mongolian"
        case .bs: return "Bosnian"
        case .kk: return "Kazakh"
        case .sq: return "Albanian"
        case .sw: return "Swahili"
        case .gl: return "Galician"
        case .mr: return "Marathi"
        case .pa: return "Punjabi"
        case .si: return "Sinhala"
        case .km: return "Khmer"
        case .sn: return "Shona"
        case .yo: return "Yoruba"
        case .so: return "Somali"
        case .af: return "Afrikaans"
        case .oc: return "Occitan"
        case .ka: return "Georgian"
        case .be: return "Belarusian"
        case .tg: return "Tajik"
        case .sd: return "Sindhi"
        case .gu: return "Gujarati"
        case .am: return "Amharic"
        case .yi: return "Yiddish"
        case .lo: return "Lao"
        case .uz: return "Uzbek"
        case .fo: return "Faroese"
        case .ht: return "Haitian creole"
        case .ps: return "Pashto"
        case .tk: return "Turkmen"
        case .nn: return "Nynorsk"
        case .mt: return "Maltese"
        case .sa: return "Sanskrit"
        case .lb: return "Luxembourgish"
        case .my: return "Myanmar"
        case .bo: return "Tibetan"
        case .tl: return "Tagalog"
        case .mg: return "Malagasy"
        case .as: return "Assamese"
        case .tt: return "Tatar"
        case .haw: return "Hawaiian"
        case .ln: return "Lingala"
        case .ha: return "Hausa"
        case .ba: return "Bashkir"
        case .jw: return "Javanese"
        case .su: return "Sundanese"
        }
    }
}

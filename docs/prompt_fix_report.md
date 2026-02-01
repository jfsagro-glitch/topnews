# Prompt & Fix Report

## Prompt 1
- **Source:** mosregtoday.ru article ("Неделя молитвы"...)
- **User request:** Remove navigation carousel and footer clutter so only article text remains.
- **Fix:** Added mosregtoday-specific headline and footer phrases to the junk removal list inside utils/text_cleaner.py (navigation headlines, promo blurbs, legal footer).

## Prompt 2
- **Source:** russian.rt.com article ("Медведев: власть в Европе захватила \"банда полоумных\"").
- **User request:** Strip RT navigation, service blocks, and footer metadata that still leaked into Telegram posts.
- **Fix:** Extended RT-specific filters in utils/text_cleaner.py with Cyrillic variants, ENG/DE navigation strip, BRICS topic carousel, and a block-level regex removing the share/tag section through the cookie banner.

import bleach
from bleach.css_sanitizer import CSSSanitizer

def sanitize_user_text(text):
        allowed_tags = bleach.sanitizer.ALLOWED_TAGS.union({
            'area', 'br', 'div', 'img', 'map', 'hr', 'header', 'hgroup', 'table', 'tr', 'td',
            'th', 'thead', 'tbody', 'span', 'small', 'p', 'q', 'u', 'pre',
        })
        allowed_attributes = {
            "*": ["style"], "a": ["href", "title"], "abbr": ["title"], "acronym": ["title"],
            "img": ["src", "alt", "usemap", "width", "height"], "map": ["name"],
            "area": ["shape", "coords", "alt", "href"]
        }
        allowed_css_properties = {
            "font-size", "font-style", "font-variant", "font-family", "font-weight", "color",
            "background-color", "background-image", "border", "border-color",
            "border-image", "width", "height"
        }
        css_sanitizer = CSSSanitizer(allowed_css_properties=allowed_css_properties)
        return bleach.clean(
                text,
                tags=allowed_tags,
                attributes=allowed_attributes,
                css_sanitizer=css_sanitizer)


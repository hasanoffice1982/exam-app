from django.template.response import TemplateResponse


def password_sheet_response(request, rows, title: str, back_url: str, empty_message: str = "Nothing to show."):
    """Renders the one-time handout. never cached, so passwords don't linger in the browser cache."""
    response = TemplateResponse(
        request,
        "proctoring/password_sheet.html",
        {"rows": rows, "title": title, "back_url": back_url, "empty_message": empty_message},
    )
    response["Cache-Control"] = "no-store, private"
    return response

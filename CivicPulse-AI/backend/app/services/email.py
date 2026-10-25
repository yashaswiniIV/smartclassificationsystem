import structlog

log = structlog.get_logger()


async def send_email(to: str, subject: str, body: str) -> None:
    """Dev implementation: log the email instead of sending it. Day 10 swaps this
    for a Resend call behind the same signature — nothing else changes."""
    log.info("email.send", to=to, subject=subject, body=body)


async def send_otp(to: str, otp: str) -> None:
    await send_email(
        to,
        subject="Your CivicPulse verification code",
        body=f"Your verification code is {otp}. It expires in 10 minutes.",
    )

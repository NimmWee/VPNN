package engine

import "testing"

func TestManualCaptchaSurvivesFollowingStateEvent(t *testing.T) {
	var latest Status
	sink := &eventSink{update: func(s Status) { latest = s }}
	sink.OnCaptcha("http://127.0.0.1:12345/manual-test", true)
	sink.OnState("captcha", 0, 6, "")
	if latest.CaptchaURL != "http://127.0.0.1:12345/manual-test" {
		t.Fatal("state update erased the manual CAPTCHA URL")
	}
	sink.OnCaptcha("", false)
	if latest.CaptchaURL != "" {
		t.Fatal("closed CAPTCHA URL retained")
	}
	sink.OnState("connected", 6, 6, "")
	if latest.CaptchaURL != "" {
		t.Fatal("connected state exposed an old challenge")
	}
}

#ifndef RUNNER_WINDOW_MESSAGES_H_
#define RUNNER_WINDOW_MESSAGES_H_

// Registered (not WM_APP) so a second instance can wake the first one without
// sharing a header that is compiled into two different modules: both sides call
// RegisterWindowMessageW with the same name.
constexpr wchar_t kShowWindowMessageName[] = L"ResourceHub.ShowWindow";

// Argument used by the Startup shortcut so a sign-in launch stays in the tray.
constexpr wchar_t kStartupHiddenFlag[] = L"--startup-hidden";

#endif  // RUNNER_WINDOW_MESSAGES_H_

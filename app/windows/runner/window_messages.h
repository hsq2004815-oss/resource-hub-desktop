#ifndef RUNNER_WINDOW_MESSAGES_H_
#define RUNNER_WINDOW_MESSAGES_H_

// Registered (not WM_APP) so a second instance can wake the first one without
// sharing a header that is compiled into two different modules: both sides call
// RegisterWindowMessageW with the same name.
constexpr wchar_t kShowWindowMessageName[] = L"ResourceHub.ShowWindow";

// Argument used by the Startup shortcut so a sign-in launch stays in the tray.
constexpr wchar_t kStartupHiddenFlag[] = L"--startup-hidden";

// Phase 19: Explorer right-click entry. A launch with
//   resource_hub.exe --add-folder "C:\Some Folder"
// either starts the app or forwards the folder to the running instance through
// WM_COPYDATA (payload = null-terminated UTF-16 path, dwData = kAddFolderCopyData).
constexpr wchar_t kAddFolderFlag[] = L"--add-folder";
constexpr ULONG_PTR kAddFolderCopyData = 0x52484146;  // 'RHAF'

#endif  // RUNNER_WINDOW_MESSAGES_H_

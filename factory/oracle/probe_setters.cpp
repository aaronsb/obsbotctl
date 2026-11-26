// probe_setters: calls vendor setters on the attached camera and restores
// every value it changes, to record what each setter sends.
//
// This probe WRITES to the camera. It only touches image and control
// settings the library can also read back (image values, zoom, white
// balance, exposure, focus, HDR, face AE/focus, FOV, AI mode), and for each
// one it reads the current value first, then either writes that same value
// back (a no-op) or writes a neighbouring value and immediately writes the
// original back. It never calls anything that upgrades, reboots, resets,
// renames, sleeps the device or touches its network or pairing.
//
// Each write sits in a marked window, so the oracle can tell the setter's
// packets from the getters around it:
//   [setter] write name=N call=F value=V   before the setter call F
//   [setter] sent name=N rc=R              after it returns
//   [setter] name=N before=B wrote=V after=A rc=R
// A restoring write is named N.restore. At the end the probe reads every
// setting again and prints "[setter] final name=N start=B now=A ok=0|1"
// and "[setter] restored all=0|1".
//
// With "read", the probe writes nothing: it prints each setting's current
// value as "[setter] value name=N now=A rc=R" and exits.
//
// Usage: probe_setters [detect_wait_ms] [read]
#include <chrono>
#include <cstdarg>
#include <cstdio>
#include <functional>
#include <string>
#include <thread>
#include <vector>

#include <dev/devs.hpp>

using Dev = std::shared_ptr<Device>;

static void pause_ms(int ms) { std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }

static std::string fmt(const char *f, ...) {
    char b[256];
    va_list a; va_start(a, f); std::vsnprintf(b, sizeof b, f, a); va_end(a);
    return b;
}

// A setting: how to read it as text, which values to write (write 0 is the
// value read at the start), and how to write one.
struct Setting {
    std::string name;
    std::string call;                        // the library setter
    std::function<int(std::string &)> get;   // returns rc, fills text
    std::function<int32_t(size_t)> value;    // value(i): what write i sends; value(0) is the start value
    std::function<int(int32_t)> set;
    size_t variants = 0;                     // writes besides the start value
    std::function<bool(int32_t)> writable;   // if set, the start value must pass it
    int settle_ms;
    std::string start;
    bool have = false;
};

static std::vector<Setting> all;

static void run(Setting &s) {
    int rc = s.get(s.start);
    if (rc != 0) { std::printf("[setter] skip name=%s getter rc=%d\n", s.name.c_str(), rc); return; }
    s.have = true;
    if (s.writable && !s.writable(s.value(0))) {
        std::printf("[setter] skip name=%s start=%s is not a value this setter takes\n", s.name.c_str(), s.start.c_str());
        return;
    }
    // Writes in order: each variant (if any), then the start value again.
    std::vector<size_t> order;
    for (size_t i = 1; i <= s.variants; i++) order.push_back(i);
    order.push_back(0);
    for (size_t k = 0; k < order.size(); k++) {
        size_t i = order[k];
        std::string name = (k > 0 && i == 0) ? s.name + ".restore" : s.name;
        std::string before;
        s.get(before);
        int32_t v = s.value(i);
        // The pauses keep the markers apart from the call's traffic: the
        // shim timestamps a printed line when its pipe reader gets it.
        std::printf("[setter] write name=%s call=%s value=%d\n", name.c_str(), s.call.c_str(), v);
        pause_ms(50);
        int wrc = s.set(v);
        pause_ms(50);
        std::printf("[setter] sent name=%s rc=%d\n", name.c_str(), wrc);
        pause_ms(s.settle_ms);
        std::string after;
        int grc = s.get(after);
        std::printf("[setter] name=%s before=%s wrote=%d after=%s rc=%d get_rc=%d\n", name.c_str(), before.c_str(), v,
                    after.c_str(), wrc, grc);
    }
}

// An int-valued setting read and written through the library.
static void add_int(const std::string &name, const std::string &call, std::function<int(int32_t &)> get, std::function<int(int32_t)> set,
                    bool vary, int32_t lo, int32_t hi, int settle = 200, int32_t step = 1) {
    Setting s;
    s.name = name;
    s.call = call;
    s.settle_ms = settle;
    auto start = std::make_shared<int32_t>(0);
    s.get = [get, start, first = std::make_shared<bool>(true)](std::string &t) {
        int32_t v = 0;
        int rc = get(v);
        if (*first && rc == 0) { *start = v; *first = false; }
        t = fmt("%d", v);
        return rc;
    };
    // Values derive from the start value, which run() reads first.
    s.set = set;
    s.variants = vary ? 1 : 0;
    s.value = [start, lo, hi, step](size_t i) {
        if (i == 0) return *start;
        return *start + step <= hi ? *start + step : (*start - step >= lo ? *start - step : *start);
    };
    all.push_back(s);
}

static void add_bool(const std::string &name, const std::string &call, std::function<int(bool &)> get, std::function<int(bool)> set, bool vary,
                     int settle = 300) {
    add_int(name, call, [get](int32_t &v) { bool b = false; int rc = get(b); v = b; return rc; },
            [set](int32_t v) { return set(v != 0); }, vary, 0, 1, settle);
}

int main(int argc, char **argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);  // unbuffered, so the shim timestamps each line when printed
    int wait_ms = argc > 1 ? std::stoi(argv[1]) : 6000;
    bool read_only = argc > 2 && std::string(argv[2]) == "read";
    Devices::get().setEnableMdnsScan(false);
    pause_ms(wait_ms);
    auto list = Devices::get().getDevList();
    if (list.empty()) { std::printf("[setter] no device\n"); return 1; }
    Dev d = list.front();
    std::printf("[setter] product=%d version=%s\n", static_cast<int>(d->productType()), d->devVersion().c_str());

    // Image values, through the library (0..100): vary and restore.
    add_int("brightness", "cameraSetImageBrightnessR", [d](int32_t &v) { return d->cameraGetImageBrightnessR(v); },
            [d](int32_t v) { return d->cameraSetImageBrightnessR(v); }, true, 0, 100);
    add_int("contrast", "cameraSetImageContrastR", [d](int32_t &v) { return d->cameraGetImageContrastR(v); },
            [d](int32_t v) { return d->cameraSetImageContrastR(v); }, true, 0, 100);
    add_int("saturation", "cameraSetImageSaturationR", [d](int32_t &v) { return d->cameraGetImageSaturationR(v); },
            [d](int32_t v) { return d->cameraSetImageSaturationR(v); }, true, 0, 100);
    add_int("hue", "cameraSetImageHueR", [d](int32_t &v) { return d->cameraGetImageHueR(v); },
            [d](int32_t v) { return d->cameraSetImageHueR(v); }, true, 0, 100);
    add_int("sharpness", "cameraSetImageSharpR", [d](int32_t &v) { return d->cameraGetImageSharpR(v); },
            [d](int32_t v) { return d->cameraSetImageSharpR(v); }, true, 0, 100);

    // Zoom (normalised 1.0..2.0, carried here in hundredths): vary and restore.
    add_int("zoom", "cameraSetZoomAbsoluteR", [d](int32_t &v) { float f = 0; int rc = d->cameraGetZoomAbsoluteR(f); v = (int32_t)(f * 100 + 0.5f); return rc; },
            [d](int32_t v) { return d->cameraSetZoomAbsoluteR(v / 100.0f); }, true, 100, 200, 800, 20);

    // Toggles the camera reports back: vary and restore.
    add_bool("aeLock", "cameraSetAELockR", [d](bool &b) { return d->cameraGetAELockR(b); }, [d](bool b) { return d->cameraSetAELockR(b); }, true);
    add_bool("faceAE", "cameraSetFaceAER", [d](bool &b) { return d->cameraGetFaceAER(b); }, [d](bool b) { return d->cameraSetFaceAER(b ? 1 : 0); }, true);

    // Modes and exposure parameters: write the value read back (no-op).
    add_int("wdr", "cameraSetWdrR", [d](int32_t &v) { return d->cameraGetWdrR(v); }, [d](int32_t v) { return d->cameraSetWdrR(v); }, false, 0, 0, 1500);
    add_int("antiFlick", "cameraSetAntiFlickR", [d](int32_t &v) { return d->cameraGetAntiFlickR(v); },
            [d](int32_t v) { return d->cameraSetAntiFlickR(v); }, false, 0, 0);
    add_int("mirrorFlip", "cameraSetMirrorFlipR", [d](int32_t &v) { return d->cameraGetMirrorFlipR(v); },
            [d](int32_t v) { return d->cameraSetMirrorFlipR(v); }, false, 0, 0);
    add_int("expMode", "cameraSetExposureModeR", [d](int32_t &v) { return d->cameraGetExposureModeR(v); },
            [d](int32_t v) { return d->cameraSetExposureModeR(v); }, false, 0, 0, 500);
    add_int("paeEvBias", "cameraSetPAEEvBiasR", [d](int32_t &v) { return d->cameraGetPAEEvBiasR(v); },
            [d](int32_t v) { return d->cameraSetPAEEvBiasR(v); }, false, 0, 0);
    add_int("aaeEvBias", "cameraSetAAEEvBiasR", [d](int32_t &v) { Device::DevAEEvBiasType e{}; int rc = d->cameraGetAAEEvBiasR(e); v = e; return rc; },
            [d](int32_t v) { return d->cameraSetAAEEvBiasR(static_cast<Device::DevAEEvBiasType>(v)); }, false, 0, 0);
    add_int("saeShutter", "cameraSetSAEShutterR", [d](int32_t &v) { return d->cameraGetSAEShutterR(v); },
            [d](int32_t v) { return d->cameraSetSAEShutterR(v); }, false, 0, 0);
    add_int("maeShutter", "cameraSetMAEShutterR", [d](int32_t &v) { return d->cameraGetMAEShutterR(v); },
            [d](int32_t v) { return d->cameraSetMAEShutterR(v); }, false, 0, 0);

    // Two-value settings, packed into one int for the generic steps.
    add_int("isoLimit", "cameraSetISOLimitR", [d](int32_t &v) { uint32_t a = 0, b = 0; int rc = d->cameraGetISOLimitR(a, b); v = (int32_t)(a << 16 | (b & 0xffff)); return rc; },
            [d](int32_t v) { return d->cameraSetISOLimitR((uint32_t)v >> 16, (uint32_t)v & 0xffff); }, false, 0, 0);
    add_int("whiteBalance", "cameraSetWhiteBalanceR", [d](int32_t &v) { Device::DevWhiteBalanceType t{}; int32_t p = 0; int rc = d->cameraGetWhiteBalanceR(t, p); v = (int32_t)((uint32_t)t << 16 | (p & 0xffff)); return rc; },
            [d](int32_t v) { return d->cameraSetWhiteBalanceR(static_cast<Device::DevWhiteBalanceType>((uint32_t)v >> 16), v & 0xffff); }, false, 0, 0, 500);
    add_int("focusAbsolute", "cameraSetFocusAbsolute", [d](int32_t &v) { int32_t f = 0; bool a = false; int rc = d->cameraGetFocusAbsolute(f, a); v = (a ? 1 << 16 : 0) | (f & 0xffff); return rc; },
            [d](int32_t v) { return d->cameraSetFocusAbsolute(v & 0xffff, (v >> 16) != 0); }, false, 0, 0, 500);
    add_int("exposureAbsolute", "cameraSetExposureAbsolute", [d](int32_t &v) { int32_t s = 0; bool a = false; int rc = d->cameraGetExposureAbsolute(s, a); v = (a ? 1 << 16 : 0) | (s & 0xffff); return rc; },
            [d](int32_t v) { return d->cameraSetExposureAbsolute(v & 0xffff, (v >> 16) != 0); }, false, 0, 0, 500);

    // Settings read back through the camera status: write the value read (no-op).
    auto st = [d](std::function<int32_t(const Device::CameraStatus &)> f) {
        return [d, f](int32_t &v) { pause_ms(300); v = f(d->cameraStatus()); return 0; };
    };
    add_int("faceFocus", "cameraSetFaceFocusR", st([](const Device::CameraStatus &s) { return (int32_t)s.tiny.face_auto_focus; }),
            [d](int32_t v) { return d->cameraSetFaceFocusR(v != 0); }, false, 0, 0, 500);
    add_int("fov", "cameraSetFovU", st([](const Device::CameraStatus &s) { return (int32_t)s.tiny.fov; }),
            [d](int32_t v) { return d->cameraSetFovU(static_cast<Device::FovType>(v)); }, false, 0, 0, 800);
    all.back().writable = [](int32_t v) { return v >= Device::FovType86 && v <= Device::FovType65; };  // not FovTypeNull
    add_int("imageFlipHorizon", "cameraSetImageFlipHorizonU", st([](const Device::CameraStatus &s) { return (int32_t)s.tiny.image_flip_hor; }),
            [d](int32_t v) { return d->cameraSetImageFlipHorizonU(v); }, false, 0, 0, 500);
    add_int("aiMode", "cameraSetAiModeU", st([](const Device::CameraStatus &s) { return (int32_t)(s.tiny.ai_mode << 8 | s.tiny.ai_sub_mode); }),
            [d](int32_t v) { return d->cameraSetAiModeU(static_cast<Device::AiWorkModeType>(v >> 8), v & 0xff); }, false, 0, 0, 1500);

    if (read_only) {
        for (auto &s : all) {
            std::string now;
            int rc = s.get(now);
            std::printf("[setter] value name=%s now=%s rc=%d\n", s.name.c_str(), now.c_str(), rc);
        }
        Devices::get().close();
        return 0;
    }
    for (auto &s : all) run(s);

    // Read everything back and compare with the start.
    pause_ms(500);
    bool ok_all = true;
    for (auto &s : all) {
        if (!s.have) continue;
        std::string now;
        int rc = s.get(now);
        bool ok = rc == 0 && now == s.start;
        ok_all = ok_all && ok;
        std::printf("[setter] final name=%s start=%s now=%s ok=%d\n", s.name.c_str(), s.start.c_str(), now.c_str(), ok);
    }
    std::printf("[setter] restored all=%d\n", ok_all);
    Devices::get().close();
    return ok_all ? 0 : 2;
}

// Runtime replica of qtbase commit 8148c48 (QTBUG-149612) for the bundled Qt.
//
// Qt 6.8.3–6.11.2 (and 6.10.x, which backported the defective b1ed5f6):
// QMacAccessibilityElement's removeElementsFromCache:/dealloc delete
// QAccessibleInterfaces that QAccessibleTable still caches. The next query
// from an external accessibility client (VoiceOver, AI computer-use
// services) reads freed memory and the app segfaults in libqcocoa.
// The upstream fix simply stops native elements from deleting interfaces;
// we apply the same change by swizzling. Delete this shim once the bundled
// Qt is >= 6.12.1 or >= 6.8.10.
//
// Build: clang -dynamiclib -fno-objc-arc -framework Foundation -o liboje_axfix.dylib axfix.m

#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <objc/message.h>

static Class g_cls;

static void oje_noop_removeElements(id self, SEL _cmd, NSArray *array)
{
    (void)self; (void)_cmd; (void)array;
}

static void oje_patched_dealloc(id self, SEL _cmd)
{
    // Mirrors the fixed upstream dealloc: release the synthesized child
    // arrays, never touch QAccessibleCache.
    Ivar rowsIvar = class_getInstanceVariable(g_cls, "rows");
    Ivar colsIvar = class_getInstanceVariable(g_cls, "columns");
    if (rowsIvar)
        [object_getIvar(self, rowsIvar) release];
    if (colsIvar)
        [object_getIvar(self, colsIvar) release];
    struct objc_super sup = { self, class_getSuperclass(g_cls) };
    ((void (*)(struct objc_super *, SEL))objc_msgSendSuper)(&sup, _cmd);
}

// Returns 0 when patched, 1/2/3 when the expected private API is missing
// (wrong Qt build — nothing is patched), 4 when Qt already has the fix.
int oje_axfix_install(void)
{
    g_cls = objc_getClass("QMacAccessibilityElement");
    if (!g_cls)
        return 1;

    Method removeElements =
        class_getClassMethod(g_cls, sel_registerName("removeElementsFromCache:"));
    if (!removeElements)
        return 4; // upstream fix removed this method: Qt is already fixed

    if (!class_getInstanceVariable(g_cls, "rows") ||
        !class_getInstanceVariable(g_cls, "columns"))
        return 2;

    Method dealloc = class_getInstanceMethod(g_cls, sel_registerName("dealloc"));
    if (!dealloc)
        return 3;

    method_setImplementation(removeElements, (IMP)oje_noop_removeElements);
    method_setImplementation(dealloc, (IMP)oje_patched_dealloc);
    return 0;
}

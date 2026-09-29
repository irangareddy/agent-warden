import SwiftUI

struct EventsView: View {
    @State private var events: [Event] = []

    var body: some View {
        List(events) { event in
            EventRow(event: event)
        }
        .task {
            events = await EventsAPI.shared.upcoming()
        }
    }
}

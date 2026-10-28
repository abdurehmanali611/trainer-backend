from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.auth import IsTrainerRole

from .models import (
    Client,
    Invoice,
    Payment,
    PaymentInstruction,
    SubscriptionPackage,
    SubscriptionPeriod,
)
from .serializers import (
    InvoiceSerializer,
    PaymentInstructionSerializer,
    PaymentSerializer,
    SubscriptionPackageSerializer,
    SubscriptionPeriodSerializer,
)
from .services import (
    approve_payment,
    forgive_invoice,
    reject_payment,
    transfer_invoice_period,
)


class PackageListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = SubscriptionPackageSerializer

    def get_queryset(self):
        return SubscriptionPackage.objects.filter(trainer=self.request.user, is_active=True)

    def perform_create(self, serializer):
        serializer.save(trainer=self.request.user)


class PackageDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = SubscriptionPackageSerializer

    def get_queryset(self):
        return SubscriptionPackage.objects.filter(trainer=self.request.user)


class PeriodListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = SubscriptionPeriodSerializer

    def get_queryset(self):
        qs = SubscriptionPeriod.objects.filter(client__trainer=self.request.user)
        client_id = self.request.query_params.get("client")
        if client_id:
            qs = qs.filter(client_id=client_id)
        return qs.select_related("client", "package")

    def create(self, request, *args, **kwargs):
        client = generics.get_object_or_404(
            Client, pk=request.data.get("client_id"), trainer=request.user
        )
        package = SubscriptionPackage.objects.filter(
            pk=request.data.get("package_id"), trainer=request.user
        ).first()
        start = request.data.get("start_date")
        end = request.data.get("end_date")
        is_trial = bool(request.data.get("is_trial"))
        if not start or not end:
            return Response(
                {"detail": "start_date and end_date are required."}, status=400
            )
        amount = Decimal(str(request.data.get("amount", package.price if package else 0)))
        period = SubscriptionPeriod.objects.create(
            client=client,
            package=package,
            start_date=start,
            end_date=end,
            amount=amount,
            is_trial=is_trial,
        )
        if not is_trial:
            Invoice.objects.create(
                client=client, period=period, amount=amount, due_date=start
            )
        return Response(SubscriptionPeriodSerializer(period).data, status=201)


class InvoiceListView(generics.ListAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = InvoiceSerializer

    def get_queryset(self):
        qs = Invoice.objects.filter(client__trainer=self.request.user).select_related(
            "client", "period"
        )
        inv_status = self.request.query_params.get("status")
        if inv_status and inv_status != "all":
            qs = qs.filter(status=inv_status)
        client_id = self.request.query_params.get("client")
        if client_id:
            qs = qs.filter(client_id=client_id)
        return qs


class InvoiceDetailView(generics.RetrieveAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = InvoiceSerializer

    def get_queryset(self):
        return Invoice.objects.filter(client__trainer=self.request.user).select_related(
            "client", "period"
        ).prefetch_related("payments")


class InvoiceForgiveView(APIView):
    permission_classes = [IsTrainerRole]

    def post(self, request, pk):
        invoice = generics.get_object_or_404(
            Invoice, pk=pk, client__trainer=request.user
        )
        forgive_invoice(invoice, note=request.data.get("note", ""))
        return Response(InvoiceSerializer(invoice).data)


class InvoiceTransferView(APIView):
    """Move this invoice's payment to another subscription period (Sep -> Oct)."""

    permission_classes = [IsTrainerRole]

    def post(self, request, pk):
        invoice = generics.get_object_or_404(
            Invoice, pk=pk, client__trainer=request.user
        )
        target = generics.get_object_or_404(
            SubscriptionPeriod,
            pk=request.data.get("target_period_id"),
            client__trainer=request.user,
        )
        result = transfer_invoice_period(invoice, target)
        return Response(
            {"detail": "Invoice transferred.", **result, "invoice": InvoiceSerializer(invoice).data}
        )


class PaymentListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        qs = Payment.objects.filter(client__trainer=self.request.user).select_related(
            "client", "invoice"
        )
        pay_status = self.request.query_params.get("status")
        if pay_status:
            qs = qs.filter(status=pay_status)
        return qs

    def create(self, request, *args, **kwargs):
        """Trainer can also record a manual payment (e.g. cash collected in person)."""
        invoice = generics.get_object_or_404(
            Invoice, pk=request.data.get("invoice_id"), client__trainer=request.user
        )
        payment = Payment.objects.create(
            invoice=invoice,
            client=invoice.client,
            transaction_id=request.data.get("transaction_id", "CASH"),
            channel=request.data.get("channel", "cash"),
            status="pending",
        )
        return Response(PaymentSerializer(payment).data, status=201)


class PaymentDecideView(APIView):
    permission_classes = [IsTrainerRole]

    def post(self, request, pk):
        payment = generics.get_object_or_404(
            Payment, pk=pk, client__trainer=request.user, status="pending"
        )
        if request.data.get("forgive"):
            forgive_invoice(payment.invoice, note=request.data.get("note", ""))
            return Response({"detail": "Invoice forgiven."})
        if request.data.get("approve"):
            approve_payment(payment, channel=request.data.get("channel"),
                           note=request.data.get("note", ""))
        else:
            reject_payment(payment, note=request.data.get("note", ""))
        return Response(PaymentSerializer(payment).data)


class BillingSummaryView(APIView):
    permission_classes = [IsTrainerRole]

    def get(self, request):
        today = date.today()
        month_start = today.replace(day=1)
        qs = Payment.objects.filter(client__trainer=request.user, status="approved")
        month_qs = qs.filter(decided_at__date__gte=month_start)
        collected = month_qs.aggregate(total=Sum("invoice__amount"))["total"] or 0
        pending = Payment.objects.filter(client__trainer=request.user, status="pending").count()
        pending_amount = (
            Payment.objects.filter(client__trainer=request.user, status="pending")
            .aggregate(total=Sum("invoice__amount"))["total"]
            or 0
        )
        overdue = Invoice.objects.filter(client__trainer=request.user, status="overdue").count()
        by_channel = (
            month_qs.values("channel")
            .annotate(total=Sum("invoice__amount"))
            .order_by("channel")
        )
        return Response(
            {
                "collected_this_month": float(collected),
                "pending_payments": pending,
                "pending_amount": float(pending_amount),
                "overdue_invoices": overdue,
                "by_channel": [
                    {"channel": r["channel"], "total": float(r["total"] or 0)}
                    for r in by_channel
                ],
            }
        )


class PaymentInstructionListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = PaymentInstructionSerializer

    def get_queryset(self):
        return PaymentInstruction.objects.filter(trainer=self.request.user)

    def perform_create(self, serializer):
        serializer.save(trainer=self.request.user)


class PaymentInstructionDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = PaymentInstructionSerializer

    def get_queryset(self):
        return PaymentInstruction.objects.filter(trainer=self.request.user)
